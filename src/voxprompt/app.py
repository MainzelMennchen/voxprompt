"""Einstiegspunkt: rumps-Menüleisten-App und zentraler Status (Modus, Aufnahme).

Verdrahtet in späteren Schritten die gesamte Pipeline:
Hotkey (hotkeys) -> Aufnahme (audio) -> Transkription (transcribe)
-> Modus-Dispatch (modes) -> Ausgabe (output).

Schritt 6 (aktuell): alle drei Modi sind aktiv und umschaltbar — über das
Menüleisten-Menü (aktueller Modus mit Häkchen) und über getrennte Hotkeys aus der
Config (Default ⌘⇧1/2/3). Der gewählte Modus wird im App-State gehalten; die
nächste Aufnahme läuft im aktiven Modus. Modus 3 ("Prompt-optimiert") baut aus
einem Gedanken-Dump einen Prompt, beantwortet ihn aber nicht (siehe prompt_builder.md).
"""

from __future__ import annotations

import atexit
import os
import signal
import threading
import time
import tomllib
import webbrowser
from pathlib import Path

import rumps

from voxprompt import __version__, audio, datalog, login_item, models, modes, output, transcribe, updates
from voxprompt.audio import Recorder
from voxprompt.hotkeys import HotkeyListener
from voxprompt.llm import LLMError, create_llm
from voxprompt.modes import Mode, ProcessingPhase
from voxprompt.server import LLMServerManager, build_command

IDLE_TITLE = "🎙"
REC_TITLE = "🔴"
BUSY_TITLE = "💭"
DL_TITLE = "⬇"  # mit Prozent während des Modell-Downloads

DEFAULT_WHISPER_MODEL = "mlx-community/whisper-large-v3-mlx"
DEFAULT_LANGUAGE = "de"

# Menü-Beschriftung + Reihenfolge der Modi.
MODE_LABELS: dict[Mode, str] = {
    Mode.RAW: "Roh",
    Mode.CLEANUP: "Bereinigt",
    Mode.PROMPT: "Prompt",
}
# Config-Schlüssel für die Direkt-Hotkeys je Modus.
MODE_HOTKEY_KEYS: dict[Mode, str] = {
    Mode.RAW: "mode_raw",
    Mode.CLEANUP: "mode_cleanup",
    Mode.PROMPT: "mode_prompt",
}


def _resource_dir() -> Path | None:
    """Resources-Verzeichnis im py2app-Bundle (setzt RESOURCEPATH), sonst None."""
    res = os.environ.get("RESOURCEPATH")
    return Path(res) if res else None


def _load_config() -> dict:
    """Lädt config.toml: im Bundle aus Resources, sonst CWD/Projektwurzel."""
    candidates = []
    if (res := _resource_dir()) is not None:
        candidates.append(res / "config.toml")
    candidates += [
        Path.cwd() / "config.toml",
        Path(__file__).resolve().parents[2] / "config.toml",
    ]
    for path in candidates:
        if path.is_file():
            with open(path, "rb") as f:
                return tomllib.load(f)
    print("[voxprompt] keine config.toml gefunden — Defaults werden benutzt", flush=True)
    return {}


def _menubar_icon_path() -> str | None:
    """Pfad zum Menüleisten-Template-Icon, falls vorhanden (sonst Emoji-Fallback)."""
    candidates = []
    if (res := _resource_dir()) is not None:
        candidates.append(res / "assets" / "menubar_template.png")
    candidates += [
        Path.cwd() / "assets" / "menubar_template.png",
        Path(__file__).resolve().parents[2] / "assets" / "menubar_template.png",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


class VoxPromptApp(rumps.App):
    """Menüleisten-App. Hält Aufnahme-/Verarbeitungsstatus und aktiven Modus."""

    def __init__(self) -> None:
        # Monochromes Template-Icon als Statusleisten-Icon; macOS passt es an
        # helle/dunkle Menüleiste an. Ohne Icon-Datei: Emoji-Fallback im Titel.
        icon_path = _menubar_icon_path()
        self._idle_title = "" if icon_path else IDLE_TITLE
        self._icon_path = icon_path  # für dynamischen Wechsel in _refresh_ui

        # Eigener Quit-Eintrag (statt rumps-Default), damit vor dem Beenden der
        # LLM-Server gestoppt werden kann.
        super().__init__(
            "voxprompt",
            title=self._idle_title,
            icon=icon_path,
            template=bool(icon_path),
            quit_button=None,
        )
        config = _load_config()
        hotkeys = config.get("hotkeys", {})
        transcription = config.get("transcription", {})
        audio_cfg = config.get("audio", {})
        output_cfg = config.get("output", {})
        llm_cfg = config.get("llm", {})
        updates_cfg = config.get("updates", {})

        self._whisper_model = transcription.get("whisper_model", DEFAULT_WHISPER_MODEL)
        self._language = transcription.get("primary_language", DEFAULT_LANGUAGE)
        self._vad_aggressiveness = audio_cfg.get("vad_aggressiveness", 2)
        self._min_speech_ms = audio_cfg.get("min_speech_ms", 200)
        self._auto_paste = bool(output_cfg.get("auto_paste", False))

        # Nachbearbeitung: LLM-Backend (endpoint|inprocess) + aktiver Modus.
        self._llm = create_llm(config)

        # Per-Modus Modell-Override aus Config (nur endpoint-Backend nutzt das).
        _default_model = llm_cfg.get("llm_model", "")
        self._mode_models: dict[Mode, str | None] = {
            Mode.CLEANUP: (llm_cfg.get("cleanup_model") or _default_model) or None,
            Mode.PROMPT: (llm_cfg.get("prompt_model") or _default_model) or None,
            Mode.RAW: None,
        }

        # Per-Modus Request-Parameter: der Prompt-Modus (prompt-tuner-8b) läuft mit
        # den Werten aus dem Finetune-Training (temperature 0.2, knappes Budget).
        self._mode_request_overrides: dict[Mode, dict] = {
            Mode.PROMPT: {
                "temperature": llm_cfg.get("prompt_temperature", 0.2),
                "max_tokens": llm_cfg.get("prompt_max_tokens", 800),
                "timeout": llm_cfg.get("prompt_timeout_seconds", 30),
            },
        }

        # Trainingsdaten-Logging: erfolgreiche Prompt-Modus-Paare für das nächste
        # Finetune (siehe datalog.py). Geloggt wird NUR, wenn das Prompt-Modus-Modell
        # exakt training_source_model ist (der schon trainierte prompt-tuner) —
        # Outputs anderer Modelle würden die Trainingsdaten verunreinigen.
        # Leeres training_source_model = Logging aus. Fallback-Fälle nie loggen.
        log_cfg = config.get("logging", {})
        self._training_log_path = log_cfg.get("training_log", "~/voxprompt_data/log.jsonl")
        self._training_log_label = log_cfg.get("training_log_model", "prompt-tuner-8b-v2")
        self._training_source_model = log_cfg.get("training_source_model", "")

        # Update-Hinweis (Option 1): GitHub-Release gegen __version__ prüfen und im
        # Menü melden — kein Self-Update, der Nutzer lädt das DMG selbst. Leeres
        # repo = Feature aus (kein Menüpunkt). check_interval_hours=0 = nur beim
        # Start und manuell.
        self._update_repo = updates_cfg.get("repo", "")
        self._check_updates_on_start = bool(updates_cfg.get("check_on_start", True))
        self._update_interval = float(updates_cfg.get("check_interval_hours", 24)) * 3600.0
        self._pending_update: updates.UpdateInfo | None = None
        self._update_checking = False
        self._last_update_check = time.monotonic()

        self._mode = self._parse_mode(config.get("modes", {}).get("default_mode", "cleanup"))

        # Modell-Verwaltung: schnell lokal prüfen, welche Modelle fehlen (kein Netz).
        # Whisper-Loader cachen, damit das Modell über Aufrufe im Speicher bleibt.
        models.install_session_caches()
        self._missing_models = models.missing_models(config)
        self._models_ready = not self._missing_models
        self._downloading = False
        self._dl_progress = 0.0  # 0..1

        # LLM-Server-Lifecycle nur für das endpoint-Backend (inprocess braucht keinen
        # Server). Beim Start hochfahren, beim Quit stoppen.
        self._server: LLMServerManager | None = None
        if llm_cfg.get("llm_backend", "endpoint") == "endpoint" and llm_cfg.get("manage_server", False):
            endpoint = llm_cfg.get("llm_endpoint", "http://127.0.0.1:8080/v1")
            template = llm_cfg.get("server_command", [])
            if template:
                self._server = LLMServerManager(
                    endpoint=endpoint,
                    command=build_command(template, endpoint),
                    startup_timeout=llm_cfg.get("server_startup_timeout", 30),
                )
        self._shut_down = False

        # Menü: drei Modi (aktueller mit Häkchen), Login-Item-Schalter, Quit.
        self._mode_items: dict[Mode, rumps.MenuItem] = {
            mode: rumps.MenuItem(MODE_LABELS[mode], callback=self._make_mode_callback(mode))
            for mode in MODE_LABELS
        }
        self._login_item = rumps.MenuItem(
            "Beim Anmelden starten", callback=self._toggle_login_item
        )
        # Update-Menüpunkt nur, wenn ein Repo konfiguriert ist. Titel/Callback
        # wechseln je nach Zustand (siehe _sync_update_item / _on_update_menu).
        self._update_item = (
            rumps.MenuItem("Auf Updates prüfen …", callback=self._on_update_menu)
            if self._update_repo
            else None
        )
        menu = [self._mode_items[m] for m in MODE_LABELS] + [None]
        if self._update_item is not None:
            menu.append(self._update_item)
        menu += [self._login_item, None, rumps.MenuItem("Quit", callback=self._on_quit)]
        self.menu = menu
        self._sync_mode_menu()
        self._sync_login_item()

        # Direkt-Hotkeys je Modus (z. B. ⌘⇧1/2/3) -> Moduswechsel. Laufen im
        # SELBEN Listener wie Push-to-Talk (zwei pynput-Listener crashen auf macOS).
        combos = {
            spec: self._make_mode_callback(mode, sender=False)
            for mode in MODE_HOTKEY_KEYS
            if (spec := hotkeys.get(MODE_HOTKEY_KEYS[mode]))
        }

        self._recorder = Recorder()
        self._processing = False
        self._processing_phase: ProcessingPhase | None = None  # Phase der Nachbearbeitungspipeline
        self._listener = HotkeyListener(
            push_to_talk=hotkeys.get("push_to_talk", "<alt_r>"),
            on_press=self._start_recording,
            on_release=self._stop_recording,
            mode=hotkeys.get("push_to_talk_mode", "hold"),
            combos=combos,
        )

        # Icon-/Menü-Status main-thread-sicher aktualisieren: die Hotkey-Callbacks
        # laufen im pynput-Thread, UI-Updates müssen aber auf den Main-Thread.
        self._status_timer = rumps.Timer(self._refresh_ui, 0.2)

    @staticmethod
    def _parse_mode(value: str) -> Mode:
        try:
            return Mode(value)
        except ValueError:
            print(f"[voxprompt] unbekannter Modus {value!r} — nutze 'cleanup'", flush=True)
            return Mode.CLEANUP

    def run(self) -> None:  # type: ignore[override]
        self._status_timer.start()
        self._listener.start()
        # LLM-Server im Hintergrund hochfahren, damit das Icon sofort erscheint.
        if self._server is not None:
            threading.Thread(target=self._start_server, daemon=True).start()
        # First-Run-Modell-Check kurz nach Start (auf dem Main-Thread, damit der
        # Onboarding-Dialog laufen kann). Einmalig.
        if self._missing_models:
            self._firstrun_timer = rumps.Timer(self._first_run_check, 0.5)
            self._firstrun_timer.start()
        # Update-Check im Hintergrund (blockiert den Start nicht).
        if self._update_repo and self._check_updates_on_start:
            self._start_update_check(notify_if_current=False)
        self._register_exit_hooks()
        super().run()

    # --- First-Run: Modelle laden ---

    def _first_run_check(self, timer: "rumps.Timer") -> None:
        timer.stop()  # nur einmal
        names = ", ".join(name for name, _ in self._missing_models)
        rumps.alert(
            title="voxprompt – Modelle werden geladen",
            message=(
                f"Beim ersten Start lädt voxprompt die benötigten Modelle "
                f"({names}, mehrere GB) von Hugging Face. Das dauert einmalig ein paar "
                f"Minuten; der Fortschritt erscheint im Menüleisten-Icon (⬇ %). "
                f"Danach kannst du normal diktieren."
            ),
            ok="Jetzt laden",
        )
        self._downloading = True
        threading.Thread(target=self._download_models, daemon=True).start()

    def _download_models(self) -> None:
        try:
            models.download_models(self._missing_models, self._on_dl_progress)
            self._models_ready = True
            self._missing_models = []
            print("[voxprompt] Modelle geladen", flush=True)
            self._notify("Modelle bereit", "Du kannst jetzt diktieren.")
        except Exception as exc:
            print(f"[voxprompt] Modell-Download fehlgeschlagen: {exc}", flush=True)
            self._notify("Modell-Download fehlgeschlagen", str(exc))
        finally:
            self._downloading = False
            self._dl_progress = 0.0

    def _on_dl_progress(self, _label: str, done: int, total: int) -> None:
        self._dl_progress = (done / total) if total else 0.0

    # --- LLM-Server-Lifecycle ---

    def _start_server(self) -> None:
        try:
            result = self._server.ensure_running()
            if result == "started":
                print("[voxprompt] LLM-Server gestartet", flush=True)
            else:
                print("[voxprompt] LLM-Server bereits aktiv — übernommen", flush=True)
        except Exception as exc:
            print(f"[voxprompt] LLM-Server-Start fehlgeschlagen: {exc}", flush=True)
            self._notify("LLM-Server", f"Start fehlgeschlagen: {exc}")

    def _register_exit_hooks(self) -> None:
        """Cleanup bei Quit, Signalen (launchctl unload, kill, Ctrl-C) und Exit."""
        atexit.register(self._shutdown)
        # Der 0.2-s-Timer pumpt den Main-Thread, daher greifen Python-Signalhandler
        # auch während der Cocoa-Eventloop.
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, self._on_signal)
            except (ValueError, OSError):
                pass  # nicht im Main-Thread o. ä.

    def _on_signal(self, _signum, _frame) -> None:  # noqa: ANN001
        self._shutdown()
        rumps.quit_application()

    def _on_quit(self, _sender) -> None:  # noqa: ANN001
        self._shutdown()
        rumps.quit_application()

    def _shutdown(self) -> None:
        """Idempotenter Cleanup: Hotkey-Listener stoppen, eigenen LLM-Server beenden."""
        if self._shut_down:
            return
        self._shut_down = True
        try:
            self._listener.stop()
        except Exception:
            pass
        if self._server is not None:
            try:
                if self._server.owned:
                    print("[voxprompt] stoppe LLM-Server (Modell wird entladen) …", flush=True)
                self._server.shutdown()
            except Exception as exc:
                print(f"[voxprompt] LLM-Server-Stop fehlgeschlagen: {exc}", flush=True)

    # --- Modus-Umschaltung ---

    def _make_mode_callback(self, mode: Mode, sender: bool = True):
        """Callback-Fabrik: Menü-Callbacks bekommen einen sender-Arg, Hotkeys nicht."""
        if sender:
            return lambda _sender: self._set_mode(mode)
        return lambda: self._set_mode(mode)

    def _set_mode(self, mode: Mode) -> None:
        if mode == self._mode:
            return
        self._mode = mode
        print(f"[voxprompt] Modus: {mode.value}", flush=True)
        self._notify("Modus", MODE_LABELS[mode])
        # Häkchen wird vom Timer (Main-Thread) synchronisiert.

    def _sync_mode_menu(self) -> None:
        for mode, item in self._mode_items.items():
            item.state = 1 if mode == self._mode else 0

    # --- Login-Item (Start beim Anmelden) ---

    def _sync_login_item(self) -> None:
        """Häkchen am Login-Item-Menüpunkt an den SMAppService-Status angleichen."""
        try:
            self._login_item.state = 1 if login_item.is_enabled() else 0
        except Exception:
            self._login_item.state = 0

    def _toggle_login_item(self, _sender) -> None:  # noqa: ANN001
        if not login_item.usable():
            # Im Dev-Betrieb (kein .app-Bundle) nicht möglich.
            self._notify(
                "Start beim Anmelden",
                "Funktioniert nur in der installierten voxprompt.app.",
            )
            self._sync_login_item()
            return
        try:
            want = not login_item.is_enabled()
            login_item.set_enabled(want)
            print(f"[voxprompt] Login-Item {'aktiviert' if want else 'deaktiviert'}", flush=True)
            self._notify(
                "Start beim Anmelden",
                "aktiviert" if want else "deaktiviert",
            )
        except Exception as exc:
            print(f"[voxprompt] Login-Item-Fehler: {exc}", flush=True)
            self._notify("Start beim Anmelden – Fehler", str(exc))
        finally:
            self._sync_login_item()

    # --- Pipeline-Callbacks (laufen im pynput-Listener-Thread) ---

    def _start_recording(self) -> None:
        if not self._models_ready:
            msg = "Modelle werden noch geladen …" if self._downloading else "Modelle nicht bereit"
            print(f"[voxprompt] {msg} — Aufnahme verschoben", flush=True)
            self._notify("Noch nicht bereit", msg)
            return
        try:
            self._recorder.start()
            print("[voxprompt] Aufnahme läuft …", flush=True)
        except Exception as exc:
            self._notify("Aufnahme-Fehler", str(exc))
            print(f"[voxprompt] Aufnahme-Start fehlgeschlagen: {exc}", flush=True)

    def _stop_recording(self) -> None:
        self._processing = True  # Sofort UI auf Processing schalten (kein Idle-Flash)
        try:
            wav_path = self._recorder.stop()
        except Exception as exc:
            self._processing = False  # Fehler → zurück zu Idle
            self._notify("Aufnahme-Fehler", str(exc))
            print(f"[voxprompt] Aufnahme-Stop fehlgeschlagen: {exc}", flush=True)
            return
        if not wav_path:
            self._processing = False  # Leere Aufnahme → zurück zu Idle
            print("[voxprompt] keine Aufnahme (leer/kein Audio)", flush=True)
            return
        print(
            f"[voxprompt] WAV: {wav_path} ({self._recorder.last_duration:.1f}s)",
            flush=True,
        )
        # Transkription ist langsam -> in eigenem Thread, damit der Listener
        # responsiv bleibt und das Icon "verarbeitet" anzeigen kann.
        self._processing = True
        threading.Thread(target=self._process, args=(wav_path,), daemon=True).start()

    def _process(self, wav_path: str) -> None:
        """Pipeline: VAD -> Transkription -> Halluzinations-Guard -> Modus -> Ausgabe.

        Jede Stufe fängt ihre Fehler ab und meldet sie als Notification, statt die
        App abstürzen zu lassen. Die aktuelle Phase wird in _processing_phase gesetzt,
        damit _refresh_ui() phasen-spezifische Emoji-Titel anzeigen kann.
        """
        try:
            # 1. VAD: stille/leere Aufnahme gar nicht erst transkribieren.
            self._processing_phase = ProcessingPhase.TRANSCRIBING
            if not audio.contains_speech(
                wav_path, self._vad_aggressiveness, self._min_speech_ms
            ):
                print("[voxprompt] Stille erkannt — übersprungen", flush=True)
                self._notify("Stille", "Keine Sprache erkannt — nichts transkribiert.")
                return

            # 2. Transkription.
            try:
                print("[voxprompt] transkribiere …", flush=True)
                raw = transcribe.transcribe(
                    wav_path, model=self._whisper_model, language=self._language
                )
            except Exception as exc:
                print(f"[voxprompt] Transkription fehlgeschlagen: {exc}", flush=True)
                self._notify("Transkription fehlgeschlagen", str(exc))
                return

            # 3. Halluzinations-Guard: leeres/unsicheres Transkript verwerfen.
            if not raw or transcribe.looks_like_hallucination(raw):
                print(f"[voxprompt] verworfen (Halluzination/leer): {raw!r}", flush=True)
                self._notify("Verworfen", "Unsicheres oder leeres Transkript verworfen.")
                return

            # 4. Nachbearbeitung im aktiven Modus; LLM-Fehler -> Rohtext-Fallback.
            self._processing_phase = {
                Mode.RAW: ProcessingPhase.RAW_DONE,
                Mode.CLEANUP: ProcessingPhase.CLEANING,
                Mode.PROMPT: ProcessingPhase.PROMPTING,
            }[self._mode]
            try:
                model_for_mode = self._mode_models.get(self._mode)
                final = modes.process(
                    self._mode,
                    raw,
                    self._llm,
                    model_override=model_for_mode,
                    request_overrides=self._mode_request_overrides.get(self._mode),
                )
                title = "Text bereit – einfügen mit ⌘V"
                if (
                    self._mode == Mode.PROMPT
                    and self._training_source_model
                    and model_for_mode == self._training_source_model
                ):
                    # Erfolgreiches Optimierer-Paar als Trainingsdatum sichern —
                    # nur wenn wirklich der trainierte prompt-tuner geantwortet hat.
                    datalog.append_pair(
                        self._training_log_path, self._training_log_label, raw, final
                    )
            except LLMError as exc:
                print(f"[voxprompt] LLM-Fehler, nutze Rohtext: {exc}", flush=True)
                self._notify("LLM nicht verfügbar – Rohtext kopiert", str(exc))
                final = raw
                title = "Rohtext bereit – einfügen mit ⌘V"
            except Exception as exc:
                print(f"[voxprompt] Nachbearbeitung fehlgeschlagen: {exc}", flush=True)
                self._notify("Nachbearbeitung fehlgeschlagen", str(exc))
                return

            # 5. Ausgabe.
            self._deliver(final, title)
        finally:
            self._processing_phase = None
            self._processing = False

    def _deliver(self, text: str, title: str) -> None:
        """Text in die Zwischenablage; optional Auto-Paste; Notification."""
        output.to_clipboard(text)
        print(f"[voxprompt] Ergebnis ({self._mode.value}) in Zwischenablage: {text}", flush=True)
        if self._auto_paste:
            try:
                output.paste()
                print("[voxprompt] auto-paste ausgeführt", flush=True)
            except Exception as exc:
                print(f"[voxprompt] Auto-Paste fehlgeschlagen: {exc}", flush=True)
                self._notify("Auto-Paste fehlgeschlagen", f"{exc} (Text liegt in der Zwischenablage)")
        preview = text if len(text) <= 80 else text[:77] + "…"
        self._notify(title, preview)

    # --- Update-Hinweis (Option 1: melden, kein Self-Update) ---

    def _start_update_check(self, notify_if_current: bool) -> None:
        """Startet einen Update-Check im Hintergrund (mehrfach-aufruf-sicher)."""
        if self._update_checking or not self._update_repo:
            return
        self._update_checking = True
        threading.Thread(
            target=self._check_updates, args=(notify_if_current,), daemon=True
        ).start()

    def _check_updates(self, notify_if_current: bool) -> None:
        """Fragt GitHub ab; bei neuerer Version -> Notification + Menü-Hinweis."""
        try:
            info = updates.check_for_update(self._update_repo)
            if info is not None:
                self._pending_update = info
                print(f"[voxprompt] Update verfügbar: {info.version} ({info.url})", flush=True)
                self._notify(
                    "Update verfügbar",
                    f"voxprompt {info.version} ist verfügbar — im Menü herunterladen.",
                )
            elif notify_if_current:
                self._notify("Kein Update", f"voxprompt {__version__} ist aktuell.")
        except Exception as exc:  # updates.* wirft eigentlich nie
            print(f"[voxprompt] Update-Check fehlgeschlagen: {exc}", flush=True)
        finally:
            self._update_checking = False

    def _on_update_menu(self, _sender) -> None:  # noqa: ANN001
        """Menü-Klick: bei bekanntem Update die Release-Seite öffnen, sonst prüfen."""
        if self._pending_update is not None:
            webbrowser.open(self._pending_update.url)
            return
        self._notify("Update-Prüfung", "Suche nach Updates …")
        self._start_update_check(notify_if_current=True)

    def _sync_update_item(self) -> None:
        """Menü-Titel an den Update-Status angleichen (läuft auf dem Main-Thread)."""
        if self._update_item is None:
            return
        if self._pending_update is not None:
            want = f"⬆︎ Update auf {self._pending_update.version} laden"
        else:
            want = "Auf Updates prüfen …"
        if self._update_item.title != want:
            self._update_item.title = want
        # Periodischer Re-Check (nur wenn Intervall gesetzt und kein Update offen).
        if (
            self._update_interval > 0
            and self._pending_update is None
            and not self._update_checking
            and time.monotonic() - self._last_update_check >= self._update_interval
        ):
            self._last_update_check = time.monotonic()
            self._start_update_check(notify_if_current=False)

    # --- UI ---

    def _refresh_ui(self, _timer: "rumps.Timer") -> None:
        idle = not self._downloading and not self._recorder.is_recording and not self._processing

        # Titel + Icon bestimmen — Emoji-Titel für alle Nicht-Idle-Zustände.
        if self._downloading:
            desired = f"{DL_TITLE}{int(self._dl_progress * 100)}%"
            want_icon = None

        elif self._recorder.is_recording:
            # Recording: roter Punkt als Titel (Emoji), kein Icon.
            desired = REC_TITLE
            want_icon = None

        elif self._processing:
            # Processing: phasen-spezifisches Emoji als Titel.
            phase_emoji = {
                ProcessingPhase.TRANSCRIBING: "⏳",
                ProcessingPhase.CLEANING: "🧹",
                ProcessingPhase.PROMPTING: "✏️",
                ProcessingPhase.RAW_DONE: BUSY_TITLE,
            }.get(self._processing_phase, BUSY_TITLE)
            desired = phase_emoji
            want_icon = None

        else:
            # Idle-Zustand.
            desired = self._idle_title  # "" wenn Icon da, sonst "🎙"
            want_icon = self._icon_path

        # UI aktualisieren wenn nötig.
        if self.title != desired or self.icon != want_icon:
            self.icon = want_icon
            self.title = desired

        self._sync_mode_menu()
        self._sync_update_item()
        # Login-Item-Status seltener prüfen (SMAppService-Aufruf), ~alle 2.4 s.
        self._tick = getattr(self, "_tick", 0) + 1
        if self._tick % 12 == 0:
            self._sync_login_item()

    def _notify(self, title: str, message: str) -> None:
        """Menüleisten-Notification; fällt im Dev-Betrieb (ohne App-Bundle) auf Konsole zurück."""
        try:
            rumps.notification("voxprompt", title, message)
        except Exception:
            print(f"[voxprompt] ({title}) {message}", flush=True)


def main() -> None:
    """Konsolen-/Skript-Einstiegspunkt (`uv run voxprompt`)."""
    VoxPromptApp().run()


if __name__ == "__main__":
    main()
