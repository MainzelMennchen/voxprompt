"""Ausgabe des Ergebnistexts (Schritt 3, erweitert in Schritt 7).

Schreibt Text in die Zwischenablage (pyperclip) und kann ihn optional per
simuliertem Cmd+V direkt ins fokussierte Feld einfügen (auto_paste-Flag).
"""

from __future__ import annotations

import time

import pyperclip
from pynput.keyboard import Controller, Key

# Ein Controller zum Senden von Tasten (kein Listener -> kein macOS-Konflikt
# mit dem Hotkey-Listener).
_keyboard = Controller()


def to_clipboard(text: str) -> None:
    """Kopiert Text in die Zwischenablage."""
    pyperclip.copy(text)


def paste() -> None:
    """Fügt per simuliertem Cmd+V ins aktuell fokussierte Feld ein (Schritt 7).

    Setzt voraus, dass der gewünschte Text bereits in der Zwischenablage liegt.
    Braucht auf macOS die Berechtigung "Bedienungshilfen" (Accessibility).
    """
    # Kurze Pause, damit die Zwischenablage sicher gesetzt ist, bevor eingefügt wird.
    time.sleep(0.05)
    with _keyboard.pressed(Key.cmd):
        _keyboard.press("v")
        _keyboard.release("v")
