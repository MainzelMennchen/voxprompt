"""Tests für die VAD-Stufe (Schritt 7)."""

from __future__ import annotations

import numpy as np
import soundfile as sf

import voxprompt.audio as audio


def _write(tmp_path, data: np.ndarray, sr: int = 16_000) -> str:
    path = tmp_path / "x.wav"
    sf.write(path, data, sr, subtype="PCM_16")
    return str(path)


def test_stille_keine_sprache(tmp_path) -> None:
    silent = np.zeros(16_000, dtype=np.float32)  # 1 s Stille
    assert audio.contains_speech(_write(tmp_path, silent)) is False


def test_zu_kurz_ist_leer(tmp_path) -> None:
    tiny = np.zeros(100, dtype=np.float32)  # < eine VAD-Frame
    assert audio.contains_speech(_write(tmp_path, tiny)) is False


def test_energy_fallback_erkennt_lautes_signal(tmp_path, monkeypatch) -> None:
    # webrtcvad ausschalten -> Energie-Fallback erzwingen
    monkeypatch.setattr(audio, "webrtcvad", None)
    rng = np.random.default_rng(0)
    loud = (0.2 * rng.standard_normal(16_000)).astype(np.float32)
    assert audio.contains_speech(_write(tmp_path, loud)) is True
    silent = np.zeros(16_000, dtype=np.float32)
    assert audio.contains_speech(_write(tmp_path, silent)) is False
