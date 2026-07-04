"""Globale Hotkeys / Push-to-Talk (Schritt 2, erweitert in Schritt 6).

Globaler Push-to-Talk-Hotkey über pynput: eine einzelne dedizierte Taste
(konfigurierbar, Default rechte Wahltaste). Halten = Aufnahme, Loslassen = Stop.
Fallback auf Toggle, falls Hold-to-Talk im Test flakey ist. Zusätzlich optionale
Tastenkombinationen (z. B. ⌘⇧1/2/3) für die Modus-Umschaltung.

Wichtig (macOS): Es läuft bewusst nur EIN pynput-Listener. Zwei parallele Listener
rufen die nicht thread-sichere Carbon-Keycode-API gleichzeitig auf und lassen den
Prozess mit SIGABRT abstürzen. Combos werden daher im selben Listener über
pynput-HotKey-Matcher behandelt.

pynput braucht die Berechtigung "Eingabeüberwachung" (Input Monitoring) für die
App/den Terminal-Prozess, sonst kommen keine Tastenevents an.
"""

from __future__ import annotations

from typing import Callable

from pynput import keyboard


def parse_key(spec: str) -> "keyboard.Key | keyboard.KeyCode":
    """Wandelt einen Config-String in ein pynput-Key-Objekt.

    Formate: "<alt_r>" / "<cmd>" (benannte Sondertaste) oder ein einzelnes
    Zeichen wie "a". Wirft ValueError bei unbekanntem Namen.
    """
    s = spec.strip()
    if s.startswith("<") and s.endswith(">"):
        name = s[1:-1]
        try:
            return getattr(keyboard.Key, name)
        except AttributeError as exc:
            raise ValueError(f"Unbekannte Taste: {spec!r}") from exc
    if len(s) == 1:
        return keyboard.KeyCode.from_char(s)
    raise ValueError(f"Hotkey-Spec nicht erkannt: {spec!r} (z. B. '<alt_r>' oder 'a')")


def _safe(callback: Callable[[], None]) -> None:
    try:
        callback()
    except Exception as exc:  # Listener-Thread darf nicht sterben
        print(f"[hotkeys] callback error: {exc}", flush=True)


class HotkeyListener:
    """Ein einziger globaler Listener für Push-to-Talk UND die Modus-Combos.

    mode="hold":   Drücken -> on_press, Loslassen -> on_release.
    mode="toggle": jedes Drücken wechselt zwischen on_press und on_release.
    Tasten-Auto-Repeat (gedrückt halten feuert mehrfach 'press') wird dedupliziert.

    combos: {"<cmd>+<shift>+1": callback, ...} — beim Auslösen wird der jeweilige
    Callback aufgerufen (für die Modus-Umschaltung).
    """

    def __init__(
        self,
        push_to_talk: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
        mode: str = "hold",
        combos: dict[str, Callable[[], None]] | None = None,
    ) -> None:
        self._target = parse_key(push_to_talk)
        self._ptt_press = on_press
        self._ptt_release = on_release
        self._mode = mode if mode in ("hold", "toggle") else "hold"
        self._listener: keyboard.Listener | None = None
        self._held = False   # physische Taste aktuell gedrückt (Auto-Repeat-Schutz)
        self._active = False  # Toggle-Zustand (läuft die Aufnahme?)

        # Combos als pynput-HotKey-Matcher (werden im selben Listener gefüttert).
        self._hotkeys: list[keyboard.HotKey] = []
        for spec, callback in (combos or {}).items():
            self._hotkeys.append(
                keyboard.HotKey(keyboard.HotKey.parse(spec), self._wrap(callback))
            )

    @staticmethod
    def _wrap(callback: Callable[[], None]) -> Callable[[], None]:
        return lambda: _safe(callback)

    def _matches(self, key) -> bool:  # noqa: ANN001
        return key == self._target

    def _canonical(self, key):  # noqa: ANN001
        return self._listener.canonical(key) if self._listener else key

    # --- Listener-Callbacks (laufen im pynput-Thread) ---

    def _on_press(self, key) -> None:  # noqa: ANN001
        canonical = self._canonical(key)
        for hotkey in self._hotkeys:
            hotkey.press(canonical)
        if self._matches(key) and not self._held:
            self._held = True
            if self._mode == "toggle":
                self._active = not self._active
                _safe(self._ptt_press if self._active else self._ptt_release)
            else:
                _safe(self._ptt_press)

    def _on_release(self, key) -> None:  # noqa: ANN001
        canonical = self._canonical(key)
        for hotkey in self._hotkeys:
            hotkey.release(canonical)
        if self._matches(key):
            self._held = False
            if self._mode == "hold":
                _safe(self._ptt_release)

    def start(self) -> None:
        """Startet den globalen Listener (nicht blockierend)."""
        if self._listener is not None:
            return
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()

    def stop(self) -> None:
        """Stoppt den Listener."""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
