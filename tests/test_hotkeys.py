"""Tests für den Hotkey-Listener (Schritt 2/6).

Treibt die Listener-Callbacks direkt (ohne echten globalen Listener), prüft
Push-to-Talk und die Combo-Modus-Umschaltung im selben Listener.
"""

from __future__ import annotations

from pynput import keyboard

from voxprompt.hotkeys import HotkeyListener, parse_key


def test_parse_key() -> None:
    assert parse_key("<alt_r>") == keyboard.Key.alt_r
    assert parse_key("a") == keyboard.KeyCode.from_char("a")


def test_ptt_und_combo_in_einem_listener() -> None:
    ptt: list[str] = []
    combo_fired: list[str] = []

    hl = HotkeyListener(
        "<alt_r>",
        on_press=lambda: ptt.append("start"),
        on_release=lambda: ptt.append("stop"),
        mode="hold",
        combos={"<cmd>+<shift>+1": lambda: combo_fired.append("mode1")},
    )

    # Push-to-Talk: Druck/Loslassen
    hl._on_press(keyboard.Key.alt_r)
    hl._on_press(keyboard.Key.alt_r)  # Auto-Repeat -> ignoriert
    hl._on_release(keyboard.Key.alt_r)
    assert ptt == ["start", "stop"]

    # Combo ⌘⇧1: alle drei Tasten drücken -> Callback feuert
    for key in keyboard.HotKey.parse("<cmd>+<shift>+1"):
        hl._on_press(key)
    assert combo_fired == ["mode1"]
    # PTT wurde durch die Combo-Tasten nicht ausgelöst
    assert ptt == ["start", "stop"]


def test_toggle_modus() -> None:
    ev: list[str] = []
    hl = HotkeyListener(
        "<alt_r>",
        on_press=lambda: ev.append("start"),
        on_release=lambda: ev.append("stop"),
        mode="toggle",
    )
    hl._on_press(keyboard.Key.alt_r); hl._on_release(keyboard.Key.alt_r)  # -> start
    hl._on_press(keyboard.Key.alt_r); hl._on_release(keyboard.Key.alt_r)  # -> stop
    assert ev == ["start", "stop"]
