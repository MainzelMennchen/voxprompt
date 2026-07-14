# CLAUDE.md — voxprompt

Kontext für Claude Code über Sessions hinweg. Vor jedem Schritt lesen.

## Zweck

Lokales Push-to-Talk-Diktiertool für macOS als Menüleisten-App. Deutsch ist die
Matrix-/Primärsprache mit englischem Code-Switching (Fachbegriffe). Ablauf:
Taste halten → sprechen → loslassen → Transkription → optionale LLM-Nachbearbeitung
→ Text liegt in der Zwischenablage.

Drei Modi:
- **Roh** (`raw`): Rohtranskript, kein LLM.
- **Bereinigt** (`cleanup`): Transkript säubern (Interpunktion, Füllwörter,
  korrekte englische Schreibweise von Fachbegriffen) — Alltags-Default.
- **Prompt-optimiert** (`prompt`): aus einem gesprochenen Gedanken-Dump einen
  einsatzbereiten Prompt formulieren (beantwortet die Anfrage NICHT).

## Stack

- Python 3.12, [uv](https://docs.astral.sh/uv/) für Dependencies
- [rumps](https://github.com/jaredks/rumps) — Menüleisten-App
- [mlx-whisper](https://github.com/ml-explore/mlx-examples) — lokale STT (Apple Silicon)
- Lokaler OpenAI-kompatibler LLM-Endpoint (MLX-Server), Client über httpx
- pynput (globaler Hotkey), sounddevice/soundfile (Audio), pyperclip (Clipboard)

Start: `uv run voxprompt`.

## Grundprinzip

Strikt schrittweise bauen. Pro Schritt nur das Nötige implementieren und den
**Akzeptanztest** bestehen, bevor es weitergeht. Abhängigkeiten erst im jeweiligen
Schritt zu `pyproject.toml` hinzufügen (hält `uv run` schlank und Fehler lokal).

## Projektstruktur

```
config.toml                 # Modelle, Endpoint, Primärsprache, Hotkeys
pyproject.toml              # uv-managed; Deps wachsen pro Schritt
CLAUDE.md                   # dieser Kontext
README.md
src/voxprompt/
  app.py                    # rumps-App, Einstiegspunkt, Modus-/Aufnahmestatus
  hotkeys.py                # globaler Push-to-Talk-Hotkey (pynput)
  audio.py                  # Aufnahme (sounddevice) -> temp WAV (soundfile)
  transcribe.py             # mlx-whisper-Wrapper, Deutsch erzwungen
  llm.py                    # OpenAI-kompat. Chat-Client (httpx)
  modes.py                  # die drei Modi, lädt System-Prompts, dispatcht
  output.py                 # Zwischenablage (pyperclip), optional Auto-Paste
  prompts/
    cleanup.md              # System-Prompt Modus 2
    prompt_builder.md       # System-Prompt Modus 3
scripts/
  com.erik.voxprompt.plist  # launchd LaunchAgent (kein Daemon!)
tests/
  test_pipeline.py
```

## 8-Schritte-Bauplan

1. **Gerüst** — Struktur, config.toml, pyproject.toml, CLAUDE.md, Modul-Stubs.
   Minimale rumps-App mit Icon + "Quit".
   *Akzeptanz:* `uv run voxprompt` zeigt ein Menüleisten-Icon, beendbar über "Quit".
2. **Audio + Push-to-Talk** — `audio.py` (sounddevice → 16 kHz mono WAV),
   `hotkeys.py` (pynput, dedizierte Taste, Hold-to-Talk, Toggle als Fallback).
   Icon zeigt Aufnahmestatus. *Akzeptanz:* halten/sprechen/loslassen → WAV entsteht.
3. **STT + Clipboard (Modus „Roh")** — `transcribe.py` (mlx-whisper, Sprache aus
   config erzwungen), `output.py` (Clipboard). End-to-End verdrahten + Notification.
   *Akzeptanz:* deutscher Satz mit engl. Begriffen → Rohtext einfügbar.
4. **LLM-Client** — `llm.py`: `complete(system_prompt, user_text) -> str` gegen
   OpenAI-kompat. Endpoint (httpx), Timeout/Fehler sauber, base_url/model/key leicht
   umschaltbar. *Akzeptanz:* Test/Konsole bekommt eine Completion zurück.
5. **Modus 2 (Bereinigt)** — `modes.py` lädt `prompts/cleanup.md`, reicht Transkript
   durch `llm.complete()`. *Akzeptanz:* unsauberes Diktat → sauberer Text, Inhalt unverändert.
6. **Modus 3 + Umschaltung** — `prompts/prompt_builder.md`, Modus 3 verdrahten;
   Modusauswahl im Menü (aktueller markiert) + getrennte Hotkeys (Cmd+Shift+1/2/3).
   *Akzeptanz:* alle drei Modi per Menü/Hotkey; Modus 3 baut Prompt, beantwortet nicht.
7. **Hardening** — VAD/Stille-Trim (kein Geistertext bei Stille),
   Whisper-Halluzinations-Guard, optionales Auto-Paste (config-Flag),
   durchgängiges Fehler-Handling per Menüleisten-Notification statt Absturz.
8. **LaunchAgent** — `scripts/com.erik.voxprompt.plist` als LaunchAgent (kein Daemon),
   RunAtLoad + KeepAlive, nach `~/Library/LaunchAgents/`. README: laden via launchctl
   + nötige Berechtigungen (Mikrofon, Bedienungshilfen, Eingabeüberwachung).

## Aktueller Stand

**Schritt 3 abgeschlossen — Tool ist ab jetzt nutzbar (Modus „Roh").** `transcribe.py`
(`transcribe()`: lädt WAV via soundfile als float32-mono-Array und gibt es an
`mlx_whisper.transcribe()` — bewusst Array statt Pfad, um die ffmpeg-Abhängigkeit zu
umgehen; Modell + Sprache aus Config, Deutsch erzwungen) und `output.py`
(`to_clipboard()` via pyperclip; `paste()` weiterhin Stub für Schritt 7) sind fertig.
`app.py` verdrahtet den Ende-zu-Ende-Fluss: Loslassen → WAV → Transkription **im
Worker-Thread** (Listener bleibt responsiv) → Rohtext in die Zwischenablage →
Menüleisten-Notification („Text bereit – einfügen mit ⌘V"; Fallback auf Konsole, falls
kein App-Bundle). Icon-Zustände: 🎙 idle / 🔴 Aufnahme / 💭 verarbeitet.
Verifiziert: Clipboard-Roundtrip, echte Transkription via `say`-Audio mit Tiny-Modell
(Deutsch erzwungen, garbled Englisch wie erwartet → LLM säubert in Schritt 5), App bootet.
**Hinweis:** Erster echter Lauf lädt `whisper-large-v3-mlx` (~3 GB) von HF.

**Schritt 4 abgeschlossen.** `llm.py`: `LLMClient(base_url, model, api_key="",
timeout_seconds=60, transport=None)` gegen einen OpenAI-kompatiblen `/chat/completions`-
Endpoint über httpx. `complete(system_prompt, user_text) -> str`; volle URL pro Request
(kein base_url-Join → `/v1` bleibt erhalten). Klartext-Fehler über die Exception `LLMError`
(nicht erreichbar / Timeout / HTTP-Status / unerwartete Antwort) — gedacht für die
Menüleisten-Notification, kein stiller Absturz. `from_config(config)`-Factory; base_url/
model/key leicht umschaltbar. `transport`-Param nur für Tests. Verifiziert: 6 pytest
(MockTransport: Happy-Path, Auth-Header, ConnectError, HTTP 500, kaputte Antwort) +
echter HTTP-Round-Trip gegen Stub-Server + saubere Fehlermeldung gegen down-Endpoint.
**Noch nicht in `app.py` verdrahtet** — das passiert in Schritt 5 (modes nutzt den Client;
`LLMError`-Text geht dann via `_notify` in die Menüleiste).

**Schritt 5 abgeschlossen — Modus 2 ("Bereinigt") verdrahtet.** `modes.py`:
`Mode` (raw/cleanup/prompt), `load_prompt(name)` (lädt aus `prompts/`, `lru_cache`),
`process(mode, transcript, llm)` — raw reicht unverändert durch (kein LLM), cleanup/prompt
schicken den Transkript-Text mit dem passenden System-Prompt durch `llm.complete()`.
`app.py` baut `LLMClient.from_config()` + aktiven Modus (`[modes] default_mode`, Default
cleanup) und schiebt den Rohtext nach der Transkription durch `_postprocess()` vor der
Zwischenablage. Bei `LLMError` graceful Fallback: **Rohtext** wird kopiert + Notification
"LLM nicht verfügbar – Rohtext kopiert". Verifiziert: 10 pytest (inkl. modes-Wiring mit
Fake-LLM: cleanup lädt `cleanup.md`, prompt lädt `prompt_builder.md`, raw ruft kein LLM) +
echter HTTP-Stub-Roundtrip (cleanup-Prompt wird gesendet, Transkript unverändert) +
Fallback-Demo. App bootet.
**Live-Qualitätstest braucht den MLX-Server** (`uv run mlx_lm.server --model
mlx-community/Qwen3-4B-Instruct-4bit --port 8080`) — das ist der eigentliche Akzeptanztest.
Modus 3 (`process` kann es schon) ist noch NICHT in `app.py` umschaltbar — Schritt 6.

**Schritt 6 abgeschlossen — alle drei Modi aktiv + umschaltbar.** Modus 3
("Prompt-optimiert") nutzt `prompt_builder.md` über `modes.process(Mode.PROMPT, …)`.
Umschaltung in `app.py`: Menüleisten-Menü mit den drei Modi (aktueller mit Häkchen,
Sync via `_refresh_ui`-Timer auf dem Main-Thread) **und** Direkt-Hotkeys aus Config
(`mode_raw`/`mode_cleanup`/`mode_prompt`, Default ⌘⇧1/2/3) → setzen den aktiven Modus
(die nächste Aufnahme läuft darin). Verifiziert: 13 pytest (inkl. `test_hotkeys`:
PTT + Combo im selben Listener, toggle) + Combo-Parsing + App-State-Switch + Stub-
Roundtrip Modus 3 (prompt_builder wird gesendet, „NICHT beantworten"-Instruktion drin).

⚠️ **macOS-Falle (gelöst):** Modus-Combos laufen im SELBEN pynput-Listener wie
Push-to-Talk. Ein zweiter Listener (`keyboard.GlobalHotKeys` parallel zu `Listener`)
ruft die nicht thread-sichere Carbon-Keycode-API gleichzeitig auf → reproduzierbarer
**SIGABRT** (Crash beim Start, sobald Events fließen). Daher: immer nur EIN Listener;
Combos via `keyboard.HotKey`-Matcher im selben `on_press`/`on_release`.

**Schritt 7 abgeschlossen — Hardening.** (1) VAD: `audio.contains_speech()` (webrtcvad,
30-ms-Frames, `min_speech_ms`; Energie-RMS-Fallback ohne webrtcvad; fail-open bei Fehler)
gated die Transkription — Stille wird gar nicht erst transkribiert. (2) Halluzinations-
Guard: `transcribe.looks_like_hallucination()` verwirft sehr kurze, stark wiederholte und
bekannte Geisterfloskeln ("Vielen Dank.", "Untertitel…", "Amara.org" …). (3) Auto-Paste:
`output.paste()` simuliert ⌘V via pynput-`Controller` (Sender, kein Listener), nur wenn
`[output] auto_paste = true`. (4) Pipeline-Fehler: `_process` ist in Stufen (VAD →
Transkription → Guard → Modus → Ausgabe) gegliedert, jede meldet ihren Fehler per
Notification statt Crash; LLM-down → Rohtext-Fallback. Neue Config: `[audio]
vad_aggressiveness`, `min_speech_ms`. Verifiziert: 28 pytest (VAD-Silence/Energie,
Guard-Fälle) + Live-Demo Stille→False / `say`-Sprache→True. App bootet.

**Schritt 8 abgeschlossen — LaunchAgent (Projekt fertig).** `scripts/com.erik.voxprompt.plist`
ist ein LaunchAgent (kein Daemon): `RunAtLoad` + `KeepAlive` true, `ProgramArguments`
= `uv run --directory /Users/erik/dev/voxprompt voxprompt`, `EnvironmentVariables.PATH`
(launchd-Minimal-PATH), Logs nach `/tmp/voxprompt.{out,err}.log`. plist-Lint OK.
**Installiert & geladen** nach `~/Library/LaunchAgents/`; verifiziert: `launchctl load`
startet die App automatisch (in `launchctl list`), KeepAlive startet sie nach kill neu.
README enthält Install/launchctl/Berechtigungs-Anleitung. Wichtig: Berechtigungen
(Mikrofon, Eingabeüberwachung, Bedienungshilfen) gelten für den launchd-Python-Prozess,
nicht das Terminal. Für Dev-Läufe (`uv run voxprompt`) den Dienst vorher entladen
(`launchctl unload …`), sonst zwei Instanzen/zwei Menüleisten-Icons.

Runtime-Deps: rumps, sounddevice, soundfile, numpy(<2.2), pynput, mlx-whisper, pyperclip,
httpx, webrtcvad-wheels. Die System-Prompts in `prompts/` liegen final vor.
**Alle 8 Schritte abgeschlossen.**

## Phase 2 (verteilbare App) — Fortschritt

Plan: `~/Downloads/voxprompt_phase2_distribution.md` (8 Schritte: in-process LLM →
models.py → Icons/Metadaten → py2app-Bundle → Login-Item → DMG → Signier-Skript → Doku).

**Phase 2, Schritt 1 abgeschlossen — zwei LLM-Backends.** `llm.py` hat jetzt ein
`LLMBackend`-Protokoll (`complete`/`close`) und zwei Implementierungen:
- `LLMClient` ("endpoint"): bisheriger HTTP-Client (für Dev, braucht Server).
- `InProcessLLM` ("inprocess"): lädt das Modell via `mlx_lm.load` lazy in den Prozess,
  baut den Prompt mit `tokenizer.apply_chat_template(..., enable_thinking=False)` und
  generiert mit `mlx_lm.generate(max_tokens=…)`; kein HTTP/Server. Modell wird beim
  ersten `complete()` geladen und für die Session gehalten.
`create_llm(config)` wählt per `[llm] llm_backend`. `app.py` nutzt die Factory; der
LLM-Server-Lifecycle wird nur fürs endpoint-Backend aktiviert. `modes.py` kennt nur das
Protokoll. Default bleibt "endpoint" (Dev). Verifiziert: 34 pytest + In-Process-Lauf des
9B OHNE Server liefert saubere, klar unterscheidbare Modus-2/3-Ergebnisse. Neue Dep: `mlx-lm`.

**Phase 2, Schritt 2 abgeschlossen — Modell-Verwaltung (`models.py`).**
`required_models(config)` (backend-abhängig: Whisper immer, Sprachmodell nur bei
inprocess), `is_cached`/`missing_models` (lokaler HF-Cache-Check, kein Netz),
`download_model(name, repo, on_progress)` lädt fehlende Modelle. **Fortschritt:** ein
Poller misst die wachsende `blobs/`-Größe gegen `_total_size` (model_info) — backend-
unabhängig. Dafür ist **Xet deaktiviert** (`HF_HUB_DISABLE_XET=1` in `__init__.py`,
vor dem ersten hf-Import), weil der Xet-Downloader außerhalb von `blobs/` stagt und die
Anzeige sonst bis kurz vor Schluss bei 0 % hängt. `install_session_caches()` wrappt
`mlx_whisper.transcribe.load_model` mit `lru_cache` → Whisper bleibt über Aufrufe im
Speicher (sonst lädt mlx_whisper bei jedem Aufruf neu); das LLM hält InProcessLLM selbst.
`app.py`: `__init__` prüft schnell lokal (App-Start bleibt schnell), bei fehlenden
Modellen zeigt ein One-Shot-`rumps.Timer` ein Onboarding-`rumps.alert`, lädt im Thread,
zeigt `⬇NN%` im Icon und meldet „Modelle bereit"; Aufnahme ist bis dahin gesperrt.
Verifiziert: 39 pytest + Live-Download mit sichtbarem Fortschritt (0→28→70→100 %) +
Whisper im Speicher gehalten (0.47s→0.06s).

**Phase 2, Schritt 3 abgeschlossen — Icons + Metadaten.** `assets/icon.png` (1024er
App-Icon; aktuell **Platzhalter** — vom User austauschbar), daraus `assets/voxprompt.icns`
(über `.iconset` + `iconutil`). Monochromes Menüleisten-Template `assets/menubar_template.png`
(+@2x), in `app.py` als Statusleisten-Icon mit `template=True` gesetzt (macOS passt es an
helle/dunkle Leiste an); Idle-Titel ist dann leer (nur Icon), Status-Emojis (🔴/💭/⬇%)
erscheinen daneben. Fehlt die Icon-Datei → Emoji-Fallback (`🎙`). Erzeugt via
`scripts/make_icons.sh` (nutzt `sips`/`iconutil` + `scripts/gen_assets.py` mit Pillow,
dev-dep). Info.plist-Werte zentral in `build_metadata.py` (root): `BUNDLE_ID`
`de.erik.voxprompt`, Version aus `__version__`, `NSMicrophoneUsageDescription` (de),
`LSUIElement=true`, `LSMinimumSystemVersion 13.0`, `ICNS_PATH` — werden in Schritt 4 von
`setup.py` eingebunden. Verifiziert: icns valide, Template-PNG schwarz+alpha, App bootet
mit Icon, 39 pytest. **Eigenes Icon:** `assets/icon.png` ersetzen + `./scripts/make_icons.sh`.

**Phase 2, Schritt 4 abgeschlossen — py2app-Bundle (`dist/voxprompt.app`, ~600 MB ohne
Modelle).** Build: `./scripts/build_app.sh` → `setup.py` (py2app) + manueller mlx-Copy.
`app_launcher.py` ist der Einstieg; `packaging/config.toml` (inprocess, manage_server=false)
wird als `config.toml` in Resources gelegt; `app.py` findet config/Icon im Bundle über
`os.environ["RESOURCEPATH"]`. **Akzeptanz erfüllt & verifiziert:** echte Inferenz aus dem
Bundle (Bundle-eigener `Contents/MacOS/python` mit `env -i` + `PYTHONHOME=Resources`,
kein venv) — Whisper transkribiert (3.8s) UND das 9B-LLM antwortet sauber (31.7s); GUI
startet, Menüleisten-Icon erscheint.

Die py2app-Stolpersteine (alle in setup.py/build_app.sh gelöst — beim nächsten Build wichtig):
1. **setuptools<80** nötig (81 bricht py2app); `setup_requires` entfernt.
2. py2app verbietet `install_requires` → in `Py2AppCommand.finalize_options`
   `self.distribution.install_requires = None` (kommt sonst aus pyproject `[project]`).
3. `sys.setrecursionlimit(10_000)` (modulegraph läuft sonst über bei transformers/scipy).
4. uv-Python linkt **zlib statisch** → `zlib.__file__` fehlt → Platzhalter setzen.
5. **`mlx` ist PEP-420-Namespace** (kein `__init__.py`) → modulegraph crasht → aus
   `packages` raus, in `excludes`, post-build verbatim ins Bundle kopieren (dylibs +
   `mlx.metallib`; `@loader_path/lib` bleibt portabel).
6. `packages`-Liste per `find_spec` filtern (sonst „No module named" bei fehlenden Deps).
7. **soundfile/sounddevice**: ihre nativen Dylibs (libsndfile/libportaudio) liegen in
   den Paketen `_soundfile_data`/`_sounddevice_data` — diese MÜSSEN in `packages`
   (entpackt), sonst landen die `.dylib` in der `.zip` und sind nicht dlopen-bar.
8. **torch ist NICHT nötig** (Whisper/mlx_lm laufen ohne) → in `excludes` (spart sehr viel).
Selbsttest-Skript-Muster: `Contents/MacOS/python` mit `PYTHONHOME=…/Contents/Resources`
und sauberem `env -i` startbar.

**Phase 2, Schritt 5 abgeschlossen — Login-Item via SMAppService.** `login_item.py`
(`available`/`status`/`is_enabled`/`usable`/`set_enabled`) kapselt
`SMAppService.mainAppService()` (ServiceManagement, pyobjc, macOS 13+). Menüpunkt
„Beim Anmelden starten" mit Häkchen in `app.py` (`_toggle_login_item`/`_sync_login_item`,
Status-Resync im Timer ~alle 2.4 s). Ersetzt den manuellen LaunchAgent aus Phase 1.
**Wichtig:** `usable()` darf NICHT am Status hängen (der ist anfangs auch im Bundle
'notFound'=3), sondern am Haupt-Bundle (`NSBundle.mainBundle()` muss eine bundleId haben
und auf `.app` enden). Sonst registriert `set_enabled` im Dev-Betrieb ein KAPUTTES
Login-Item auf das venv-Python (in dev wirft register KEINEN Fehler!). Darum guard in
`set_enabled` + 3 pytest, die Schalten ohne Bundle blockieren. Dep: `pyobjc-framework-
ServiceManagement` (in setup.py-`packages`). Verifiziert aus dem Bundle: usable=True,
ENABLE→status 1, DISABLE→status 0. Logout/Login selbst nicht testbar, aber status=enabled
ist der Mechanismus, mit dem macOS beim Login startet.

**Phase 2, Schritt 6 abgeschlossen — verteilbares DMG.** `scripts/make_dmg.sh` baut
`dist/voxprompt.dmg` (~192 MB komprimiert) mit `create-dmg` (brew): Volume-Icon
(`voxprompt.icns`), Applications-Symlink, Drag-to-Applications-Layout (Icon-Positionen via
.DS_Store), unsigniert. App wird in einen Staging-Ordner gelegt (create-dmg packt
Ordner-INHALT). Verifiziert: DMG mountet, zeigt App + Applications-Alias, nach
/Applications kopiert läuft die App und diktiert korrekt (Whisper 1.7s + 9B 26.4s),
GUI startet. **Gotcha:** create-dmg fährt Finder per AppleScript für das Layout —
das schlägt sporadisch mit `AppleEvent timed out (-1712)` fehl (Finder träge). Dann
bricht create-dmg ab und erzeugt KEIN DMG → einfach erneut laufen lassen (ggf. vorher
`osascript -e 'tell application "Finder" to count windows'`, um Finder zu wecken). Das
Skript macht den Erfolg an der erzeugten Datei fest, nicht am Exitcode.

## LLM-Server-Lifecycle (server.py)

`server.py` (`LLMServerManager`) startet den lokalen LLM-Server beim App-Start und
stoppt ihn beim Beenden (→ Modell wird entladen). Config: `[llm] manage_server`,
`server_command` ({host}/{port} aus `llm_endpoint`), `server_startup_timeout`.
Logik: ist beim Start schon ein Server unter `llm_endpoint` erreichbar → übernehmen
(`owned=False`, wird NICHT mitgestoppt); sonst selbst starten (`owned=True`). `app.py`
ruft `ensure_running()` in einem Hintergrund-Thread aus `run()` (Icon erscheint sofort)
und `_shutdown()` über (a) eigenen Quit-Menüpunkt, (b) `atexit`, (c) Signal-Handler
SIGTERM/SIGINT. Die Signale greifen auch während der Cocoa-Loop, weil der 0.2-s-`rumps.Timer`
den Main-Thread pumpt — getestet: `uv run voxprompt` startet mlx_lm.server auf :8080,
SIGTERM stoppt ihn wieder. Server-Log: `/tmp/voxprompt-mlx.log`.

**Wechselwirkung mit dem LaunchAgent (Schritt 8):** Der Agent läuft mit KeepAlive
dauerhaft → dann ist auch der gemanagte Server dauerhaft an (Quit → Respawn). Das
On-Demand-Start/Stop greift v. a. im Standalone-Betrieb (`uv run voxprompt`). Für
On-Demand den Agent entladen.

## Reasoning-/Thinking-Modelle (wichtig)

Qwen3.x (z. B. das auf :8080 geladene `Qwen3.5-4B-MLX-4bit`) sind **Thinking-Modelle**:
ohne Gegenmaßnahme verbrauchen sie das ganze Token-Budget für internes `reasoning` und
liefern **leeren `content`** (`finish_reason=length`) → Modus 2/3 kamen leer/fehlerhaft
zurück und Modus 3 „fühlte sich wie Modus 2" an. `llm.py` setzt daher jetzt `max_tokens`
**und** `chat_template_kwargs.enable_thinking=false` (Config: `[llm] max_tokens`,
`disable_thinking`). Wirkung getestet: mit `enable_thinking=false` ~6–10 s und ein
sauberer, von Modus 2 klar unterscheidbarer Prompt; `/no_think` im Prompt wirkt NICHT,
nur `chat_template_kwargs`. `complete()` strippt zusätzlich Inline-`<think>`-Blöcke und
meldet leeren Output klar. `llm_model` muss dem im Request angeforderten Modell
entsprechen — der mlx_lm.server läuft **ohne `--model`** und lädt das Modell dynamisch
aus dem HF-Cache (`GET /v1/models` zeigt die geladenen). Aktuell:
**`mlx-community/Qwen3.5-9B-MLX-4bit`** (Q4, ~5.6 GB, erster Request ~25 s Modell-Load,
danach ~7–11 s/Anfrage). Auf dem 9B liefert Modus 3 deutlich reichere, klar von Modus 2
unterscheidbare Prompts (inkl. Tech-Vorschlägen wie Matplotlib/pandas).

**Aktuelle Dev-Konfiguration (config.toml, Stand jetzt):** endpoint-Backend gegen
**LM Studio** auf `http://127.0.0.1:1234/v1`, Modell `qwen3.6-35b-a3b-mtp`,
`manage_server=false` (LM Studio hostet selbst; voxprompt startet/stoppt nichts).
Verifiziert: Modus 2/3 liefern saubere Ergebnisse (35B → besonders reiche Prompts);
`disable_thinking=true`/`chat_template_kwargs` wird von LM Studio problemlos akzeptiert.
Das Bundle (`packaging/config.toml`) bleibt davon unberührt (inprocess).

## Speicherort: NICHT in iCloud (wichtig — gelöstes Problem)

Das Projekt liegt unter **`/Users/erik/dev/voxprompt`** (außerhalb iCloud). Das ist Absicht.

Ursprünglich lag es unter `~/Documents/Speech to text App`. Auf dieser Maschine ist
iCloud-Sync „Schreibtisch & Dokumente" aktiv (`bird`/`fileproviderd`, `optimize-storage=1`).
iCloud verwaltete dann den ganzen Ordner inkl. `.venv` und setzte auf den `.pth`-Dateien
das macOS-Flag `UF_HIDDEN` (frisch geschrieben → nach ~8–12 s versteckt). CPython 3.12
ignoriert versteckte `.pth`-Dateien bewusst (site.py, `UF_HIDDEN`-Check) → `src/` landet
nicht auf dem Pfad → sporadisch `ModuleNotFoundError: No module named 'voxprompt'`.
Belegt per A/B-Test: identischer `.pth` in `/tmp` blieb sichtbar, der im iCloud-Ordner wurde
versteckt. Außerhalb von iCloud tritt das Problem nicht auf (verifiziert).

**Konsequenz:** Das Projekt nicht zurück nach `~/Documents`, `~/Desktop` oder einen anderen
iCloud-synchronisierten Ordner verschieben. `.venv`/Caches gehören ohnehin nie in iCloud.
- uv aktuell halten (≥ 0.11.23).
- Dev-Tools über die dev-Dependency-Group (`uv add --dev ...`, `uv run pytest`), nicht
  über `uv run --with` (Overlay-Umgebung kann den `.pth` ebenfalls verstecken).
- Falls das Symptom je wieder auftaucht (z. B. Projekt versehentlich in iCloud):
  `chflags nohidden .venv/lib/python3.12/site-packages/_editable_impl_voxprompt.pth`
  oder non-editable bauen mit `UV_NO_EDITABLE=1 uv sync`.

## Per-Modus-LLMs + Prompt-Tuner-Integration (Stand 2026-07-12)

Bereinigt und Prompt laufen über getrennte Modelle — in BEIDEN Backends:
`[llm] cleanup_model`/`prompt_model` überschreiben `llm_model` pro Modus
(leer = Default). Durchreichung: `app.py` `_mode_models` → `modes.process(
model_override=…)` → `complete(model=…)`.

**InProcess-Backend (Bundle) — Laden/Entladen statt Serverwechsel:** `InProcessLLM`
hält immer genau EIN Modell im Speicher (`_loaded_id`); fordert `complete(model=…)`
ein anderes an, wird entladen (`_unload`: Referenzen weg + `gc.collect()` +
`mx.clear_cache()`) und das neue geladen. Moduswechsel kostet einmalig ~Ladezeit
(gemessen 2–4 s aus warmem HF-Cache), RAM bleibt bei einem Modell. Bundle-Config:
cleanup = Stock-`mlx-community/Qwen3.5-9B-MLX-4bit`, prompt =
`MainzelMennchen/prompt-tuner-8b` (HF-Backup des Finetunes; MLX-4bit, von
mlx_lm direkt ladbar). `models.py required_models()` zählt im inprocess-Backend
auch cleanup_model/prompt_model (dedupliziert) → Onboarding-Download holt das
Finetune beim ersten Start mit (~4,7 GB).

**Logging-Gate:** Trainingspaare werden NUR geschrieben, wenn das Prompt-Modus-
Modell exakt `[logging] training_source_model` ist (dev: `prompt-tuner-8b`,
Bundle: `MainzelMennchen/prompt-tuner-8b`); leer = Logging aus. Outputs fremder
Modelle landen nie im Trainingslog.

**Modus 3 = Prompt-Optimierer (`prompt-tuner-8b`):** eigenes QLoRA-Finetune von
Qwen3.5-9B (lokal in LM Studio unter `erik/prompt-tuner-8b`, HF-Backup
`MainzelMennchen/prompt-tuner-8b`). `prompts/prompt_builder.md` enthält EXAKT das
System-Prompt aus dem Training — **kein Zeichen ändern** (Test sichert das byte-genau
ab). Request-Parameter aus dem Training: `prompt_temperature=0.2`,
`prompt_max_tokens=800`, `prompt_timeout_seconds=30` (via `_mode_request_overrides`
→ `request_overrides` → per-Request temperature/max_tokens/timeout in `complete()`).
Thinking ist beim prompt-tuner im Chat-Template deaktiviert (Default OFF), keine
Sonderparameter nötig.

**Trainingsdaten-Logging (`datalog.py`):** nach jedem ERFOLGREICHEN Prompt-Modus-Call
eine JSONL-Zeile an `[logging] training_log` (Default `~/voxprompt_data/log.jsonl`):
`{ts, model: "prompt-tuner-8b-v2", raw, output, final: null}` — `ensure_ascii=False`,
append-only, wirft nie (Fehler nur Konsole). Fallback-Fälle (LLM down → Rohtext)
werden NICHT geloggt. `final` ist für manuell korrigierte Endfassungen reserviert
(kein Editier-UI vorhanden → bleibt null).

⚠️ **LM-Studio-Fallen (beide verifiziert):**
1. **Stiller Modell-Fallback:** Bei unbekanntem `model`-Namen antwortet LM Studio
   einfach mit dem gerade geladenen Modell — kein Fehler! Modellnamen müssen exakt
   der ID aus `GET /v1/models` entsprechen (`prompt-tuner-8b`, nicht
   `erik/prompt-tuner-8b`; `qwen3.5-9b-mtp`, nicht der HF-Repo-Name).
2. **Thinking nicht per API abschaltbar:** Die aktuelle LM-Studio-Version ignoriert
   `chat_template_kwargs.enable_thinking`, top-level `enable_thinking`,
   `reasoning_effort` und `/no_think`. Stock-Qwen-GGUFs (qwen3.5-9b-mtp,
   qwen3.6-27b-mtp) denken daher unkontrolliert → verbrennen `max_tokens`, leerer
   content → LLMError. Cleanup auf qwen3.5-9b-mtp ist deshalb aktuell FUNKTIONAL
   KAPUTT (Rohtext-Fallback greift), bis der Thinking-Default im LM-Studio-GUI
   (Template-Edit: `is defined and` → `is not defined or`) umgestellt ist.
   prompt-tuner-8b ist immun (Template-Default beim Finetune auf OFF gedreht).

Verifiziert (2026-07-11): 53 pytest; E2E Prompt-Modus 6,5 s, strukturierter Prompt
ohne Thinking-Block, Logzeile korrekt; Fallback (Port zu) → Rohtext, keine Logzeile.
Verifiziert (2026-07-12): 55 pytest; Swap live (dev + aus dem Bundle): Cleanup auf
Stock-9B 2,3 s → Modellwechsel → Prompt auf Finetune 3,9 s, kein Reload bei gleichem
Modell, close() entlädt; Logging-Gate lässt nur das Finetune-Paar durch; App neu
gebaut (602 MB) + DMG (186 MB, Mount-Test OK). DMG-Gotcha Nr. 2: bleibt ein
rw.*.dmg-Staging-Image gemountet (Resource busy), erst `hdiutil detach` + Reste
löschen, dann neu bauen.

## Update-Hinweis (Option 1: melden, kein Self-Update) — Stand 2026-07-14

Erste Stufe der Update-Strategie: die App prüft das neueste GitHub-Release und
MELDET ein Update — sie ersetzt sich NICHT selbst (kein Sparkle, keine
Signatur-Fallen). `updates.py`: `check_for_update(repo, current=__version__) ->
UpdateInfo|None` fragt `GET /repos/{repo}/releases/latest` (httpx), vergleicht
`tag_name` mit `__version__` (`is_newer`/`_parse_version`, semver-artig, '1.2' ==
'1.2.0') und ignoriert Drafts/Prereleases. **Fehler-tolerant:** leeres repo, 404,
Netz-/Parsefehler → None, wirft NIE (der Check darf das Diktieren nie stören).

`app.py`: Menüpunkt „Auf Updates prüfen …" (nur wenn `[updates] repo` gesetzt);
bei gefundenem Update wird der Titel zu „⬆︎ Update auf vX laden" und ein Klick
öffnet die Release-Seite (`webbrowser.open`), sonst startet der Klick einen
manuellen Check. Check läuft im Hintergrund-Thread (`_start_update_check` /
`_check_updates`, `_update_checking`-Guard gegen Overlap), beim Start (`check_on_start`)
und periodisch (`check_interval_hours`, 0 = nur Start/manuell; Intervall im
`_refresh_ui`-Timer via `time.monotonic()`). Menü-Titel-Sync auf dem Main-Thread
in `_sync_update_item`. Neue Notification bei gefundenem Update. `repo` muss dem
echten GitHub-Repo entsprechen (`owner/name`); leer = kein Menüpunkt.

Verifiziert (2026-07-14): 71 pytest (16 neu: is_newer-Matrix, MockTransport für
neuer/gleich/älter/draft/prerelease/404/Netzfehler/kaputtes JSON/leeres repo) +
Live-HTTP gegen echtes Repo (UpdateInfo mit realer Version+URL) und gegen das
noch nicht existente Zielrepo (404 → None, kein Crash) + App konstruiert, Menü
enthält den Punkt, Titel flippt bei pending Update und zurück. **Nächste Stufen:**
Homebrew-Cask (Option 3) + Signier-/Notarisierungs-Pipeline (Phase-2-Schritt 7,
Voraussetzung: jedes Update muss notarisiert sein); Sparkle (Option 2) später.

## Config-Felder (config.toml)

- `[transcription] whisper_model`, `primary_language` ("de")
- `[llm] llm_endpoint`, `llm_model`, `api_key`, `timeout_seconds`, `max_tokens`,
  `disable_thinking`, `cleanup_model`, `prompt_model`, `prompt_temperature`,
  `prompt_max_tokens`, `prompt_timeout_seconds`, `manage_server`, `server_command`,
  `server_startup_timeout`, `llm_backend`
- `[modes] default_mode`
- `[hotkeys] push_to_talk`, `mode_raw`/`mode_cleanup`/`mode_prompt`
- `[output] auto_paste`
- `[logging] training_log`, `training_log_model`, `training_source_model`
- `[updates] repo`, `check_on_start`, `check_interval_hours`
