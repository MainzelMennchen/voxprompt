# BRIEFING: Menüleisten-Icons für Recording vs. LLM Processing

## ZIEL
Im macOS-Menüleisten-Icon von voxprompt unterschiedliche visuelle Zustände anzeigen:
- **Idle**: Mikrofon (Template-Icon, leerer Titel) — unverändert
- **Recording**: 🔴 roter Punkt als Emoji-Titel
- **Processing (LLM arbeitet)**: 💭 Denkblase als Emoji-Titel (mit phasen-spezifischen Varianten)

Der Übergang Recording → Processing muss flüssig sein — KEIN kurzes Aufblinken des Mikrofon-Icons dazwischen.

## DATEIEN

### 1. `src/voxprompt/modes.py`
**Neue Enum hinzufügen:**
```python
class ProcessingPhase(str, Enum):
    TRANSCRIBING = "transcribing"
    CLEANING = "cleaning"      # cleanup mode LLM
    PROMPTING = "prompting"    # prompt mode LLM
    RAW_DONE = "raw_done"      # raw mode (kein LLM)
```

### 2. `src/voxprompt/app.py`
**Änderungen:**

a) **Import**: `ProcessingPhase` aus `modes` importieren

b) **Instance-Variable** in `__init__` nach Zeile 175:
```python
self._processing_phase = None  # ProcessingPhase | None
```

c) **`_process()` Methode** (Zeilen 380–429): Phase-Tracking an jeder Pipeline-Stelle:
```python
def _process(self, wav_path: str) -> None:
    try:
        # 1. VAD
        self._processing_phase = ProcessingPhase.TRANSCRIBING
        if not audio.contains_speech(...):
            ...
            return

        # 2. Transkription
        self._processing_phase = ProcessingPhase.TRANSCRIBING
        raw = transcribe.transcribe(...)

        # 3. Halluzinations-Guard
        if not raw or transcribe.looks_like_hallucination(raw):
            ...
            return

        # 4. Modus-Dispatch (LLM)
        self._processing_phase = {
            Mode.RAW: ProcessingPhase.RAW_DONE,
            Mode.CLEANUP: ProcessingPhase.CLEANING,
            Mode.PROMPT: ProcessingPhase.PROMPTING,
        }[self._mode]
        final = modes.process(self._mode, raw, self._llm)

        # 5. Ausgabe
        self._deliver(final, title)
    finally:
        self._processing_phase = None
        self._processing = False
```

d) **`_refresh_ui()` Methode** (Zeilen 447–494): Komplett umschreiben:

```python
def _refresh_ui(self, _timer: "rumps.Timer") -> None:
    idle = not self._downloading and not self._recorder.is_recording and not self._processing

    prev_was_non_idle = getattr(self, "_prev_idle", False)
    if idle and prev_was_non_idle:
        self._just_became_idle = True
    self._prev_idle = idle

    # Titel + Icon bestimmen
    if self._downloading:
        desired = f"{DL_TITLE}{int(self._dl_progress * 100)}%"
        want_icon = getattr(self, "_last_nonidle_icon", None) or self._icon_path
        self._just_became_idle = False

    elif self._recorder.is_recording:
        # Recording: roter Punkt als Titel (Emoji), Template-Icon beibehalten
        desired = REC_TITLE
        want_icon = getattr(self, "_last_nonidle_icon", None) or self._icon_path
        self._just_became_idle = False

    elif self._processing and self._processing_phase:
        # Processing: Denkblase oder phasen-spezifisches Emoji
        phase_emoji = {
            ProcessingPhase.TRANSCRIBING: "⏳",   # Sanduhr beim Transkribieren
            ProcessingPhase.CLEANING: "🧹",       # Besen beim Bereinigen
            ProcessingPhase.PROMPTING: "✏️",      # Bleistift beim Prompt-Bauen
            ProcessingPhase.RAW_DONE: BUSY_TITLE,  # 💭 für raw (Fallback)
        }[self._processing_phase]
        desired = phase_emoji
        want_icon = getattr(self, "_last_nonidle_icon", None) or self._icon_path
        self._just_became_idle = False

    else:
        # Idle-Zustand
        desired = self._idle_title  # "" wenn Icon da, sonst "🎙"
        if self._just_became_idle:
            want_icon = getattr(self, "_last_nonidle_icon", None) or self._icon_path
        else:
            want_icon = self._icon_path

    # UI aktualisieren wenn nötig
    if self.title != desired or self.icon != want_icon:
        self.icon = want_icon
        self.title = desired

    # Nicht-Idle-Icon merken (für Idle-Übergang)
    if not idle:
        self._last_nonidle_icon = want_icon

    self._sync_mode_menu()
    self._tick = getattr(self, "_tick", 0) + 1
    if self._tick % 12 == 0:
        self._sync_login_item()
```

## FAKTEN

- **rumps Timer**: `_refresh_ui()` wird alle 200ms auf dem Main-Thread ausgeführt — UI-Updates sind thread-safe.
- **Hotkey-Callbacks** laufen im pynput-Thread, setzen aber nur State-Variablen (`_processing`, `_recorder.start()/stop()`) — keine direkten UI-Aufrufe.
- **Template-Icon**: `menubar_template.png` (22px) ist ein Mikrofon-Glyph. macOS tinted es automatisch für Light/Dark Mode. Es gibt KEINE separaten PNGs für Recording/Processing.
- **Bestehende Emoji-Konstanten** (Zeilen 32–35): `IDLE_TITLE="🎙"`, `REC_TITLE="🔴"`, `BUSY_TITLE="💭"`, `DL_TITLE="⬇"` — diese werden jetzt aktiv genutzt.
- **Flash-Prävention**: `_just_became_idle` und `_last_nonidle_icon` verhindern, dass macOS beim Übergang Nicht-Idle→Idle kurz zum Original-Mikrofon-Icon zurückspringt. Diese Logik bleibt erhalten.
- **Critical Path**: In `_stop_recording()` (Zeile 377) wird `self._processing = True` SETZT BEVOR der Thread gestartet wird — dadurch gibt es keine Lücke zwischen Recording-Stopp und Processing-Start.

## CONSTRAINTS

1. **Keine neuen PNGs generieren** — wir nutzen Emoji-Titel auf dem bestehenden Template-Icon. Das ist visuell klar unterscheidbar (🔴 vs 💭 vs ⏳ vs 🧹 vs ✏️).
2. **Bestehende Flash-Prävention beibehalten** — `_just_became_idle` und `_last_nonidle_icon` Logik muss intakt bleiben.
3. **Thread-Safety**: Nur State-Variablen werden im Background-Thread gesetzt (`_processing`, `_processing_phase`). UI-Updates passieren ausschließlich im Timer-Callback auf dem Main-Thread.
4. **Keine externen Dependencies hinzufügen** — alles was gebraucht wird ist bereits importiert oder existiert im Codebase.
5. **Python-Typen beibehalten** — Type-Hints müssen konsistent bleiben (von `__future__ import annotations`).

## AKZEPTANZ

- [ ] Idle zeigt Mikrofon-Icon mit leerem Titel (Template)
- [ ] Recording zeigt 🔴 als Emoji-Titel
- [ ] Processing/Transcribing zeigt ⏳ als Emoji-Titel
- [ ] Processing/Cleanup zeigt 🧹 als Emoji-Titel  
- [ ] Processing/Prompt zeigt ✏️ als Emoji-Titel
- [ ] Raw (kein LLM) zeigt 💭 als Emoji-Titel
- [ ] Übergang Recording→Processing: KEIN Mikrofon-Flash dazwischen
- [ ] Übergang Processing→Idle: Flash-Prävention funktioniert (bleibt beim letzten Nicht-Idle-Icon)
- [ ] Download-Zustand unverändert (⬇ + Prozent)
- [ ] `python3 -m py_compile src/voxprompt/app.py` und `python3 -m py_compile src/voxprompt/modes.py` laufen ohne Fehler
