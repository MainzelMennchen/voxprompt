"""Tests für das Trainingsdaten-Logging (datalog.py)."""

from __future__ import annotations

import json
from pathlib import Path

from voxprompt import datalog


def test_append_pair_schreibt_jsonl_zeile(tmp_path: Path) -> None:
    log = tmp_path / "sub" / "log.jsonl"  # Verzeichnis existiert noch nicht
    ok = datalog.append_pair(log, "prompt-tuner-8b-v2", "ähm rohes diktat", "Präziser Prompt")

    assert ok is True
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["model"] == "prompt-tuner-8b-v2"
    assert entry["raw"] == "ähm rohes diktat"
    assert entry["output"] == "Präziser Prompt"
    assert entry["final"] is None
    assert "T" in entry["ts"]  # ISO-Zeitstempel
    # ensure_ascii=False: Umlaute stehen roh in der Datei, nicht als \uXXXX.
    assert "ähm" in lines[0]


def test_append_pair_haengt_an(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    datalog.append_pair(log, "m", "eins", "One")
    datalog.append_pair(log, "m", "zwei", "Two")
    lines = log.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["raw"] for line in lines] == ["eins", "zwei"]


def test_append_pair_wirft_nie(tmp_path: Path) -> None:
    """Logging-Fehler dürfen den Diktat-Flow nicht stören: False statt Exception."""
    blocker = tmp_path / "datei"
    blocker.write_text("ich bin eine Datei, kein Verzeichnis")
    # Elternpfad ist eine Datei -> mkdir/open schlägt fehl -> False, keine Exception.
    ok = datalog.append_pair(blocker / "log.jsonl", "m", "raw", "out")
    assert ok is False
