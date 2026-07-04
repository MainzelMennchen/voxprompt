"""Tests für die Login-Item-Verwaltung (Phase 2, Schritt 5).

Im Dev-/Testbetrieb gibt es kein .app-Bundle — Schalten muss daher blockiert sein
(sonst würde ein kaputtes Login-Item auf das venv-Python angelegt).
"""

from __future__ import annotations

import pytest

from voxprompt import login_item


def test_framework_verfuegbar() -> None:
    assert login_item.available() is True  # ServiceManagement importierbar (macOS)


def test_nicht_nutzbar_ohne_bundle() -> None:
    assert login_item.usable() is False


def test_set_enabled_blockt_ohne_bundle() -> None:
    with pytest.raises(RuntimeError):
        login_item.set_enabled(True)
