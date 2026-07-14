"""Spracherkennung über mlx-whisper (Schritt 3) + Halluzinations-Guard (Schritt 7).

Dünner Wrapper um mlx_whisper.transcribe(). Lädt das Modell aus der Config und
erzwingt die Primärsprache (Deutsch). Gibt den reinen Transkript-String zurück.
`looks_like_hallucination()` erkennt typischen Whisper-Geistertext bei Stille.
"""

from __future__ import annotations

import re

import mlx_whisper
import numpy as np
import soundfile as sf

DEFAULT_MODEL = "mlx-community/whisper-large-v3-mlx"
SAMPLE_RATE = 16_000

# Bekannte Whisper-Halluzinationen (Untertitel-/Outro-Floskeln), die bei
# Stille auftauchen. Vergleich case-insensitiv; greift nur, wenn sie praktisch die
# GANZE Ausgabe sind (sonst könnte echter Text fälschlich verworfen werden).
_HALLUCINATION_PHRASES = (
    # German
    "vielen dank",
    "vielen dank.",
    "tschüss",
    "amara.org",
    "untertitel",
    "untertitelung des zdf für funk",
    "untertitel im auftrag des zdf",
    "untertitel der amara.org-community",
    "das war's",
    "bis zum nächsten mal",
    # English
    "thank you",
    "subtitles",
    "this is all",
    "that's it",
)


def looks_like_hallucination(text: str) -> bool:
    """True, wenn der Text wie Whisper-Geistertext aussieht (verwerfen statt einfügen)."""
    t = text.strip()
    if len(t) < 2:
        return True
    low = t.lower().strip(" .!?\"'")

    # Bekannte Floskel, die im Wesentlichen die ganze Ausgabe ist.
    for phrase in _HALLUCINATION_PHRASES:
        if low == phrase or (low.startswith(phrase) and len(low) <= len(phrase) + 4):
            return True

    # Starke Wort-/Phrasen-Wiederholung (z. B. "danke danke danke danke").
    words = re.findall(r"\w+", low)
    if len(words) >= 4 and len(set(words)) == 1:
        return True
    if len(words) >= 8 and len(set(words)) / len(words) < 0.25:
        return True

    return False


def _load_audio(wav_path: str) -> np.ndarray:
    """Liest die WAV als float32-mono-Array (16 kHz).

    Bewusst über soundfile statt über den Pfad: mlx-whisper würde für einen Pfad
    ffmpeg aufrufen; mit einem fertigen Array entfällt diese Systemabhängigkeit.
    Der Recorder schreibt bereits 16 kHz mono.
    """
    audio, sample_rate = sf.read(wav_path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sample_rate != SAMPLE_RATE:
        print(
            f"[transcribe] Warnung: {sample_rate} Hz statt {SAMPLE_RATE} Hz — "
            "Whisper erwartet 16 kHz.",
            flush=True,
        )
    return np.ascontiguousarray(audio)


def transcribe(wav_path: str, model: str = DEFAULT_MODEL, language: str = "de") -> str:
    """Transkribiert eine WAV-Datei und gibt den reinen Text zurück.

    Die Sprache wird bewusst erzwungen (Default Deutsch): Deutsch ist die
    Matrix-Sprache, englische Fachbegriffe bereinigt später das LLM (Schritt 5/6).
    Das Modell wird von mlx-whisper beim ersten Lauf von Hugging Face geladen
    und danach gecacht.
    """
    audio = _load_audio(wav_path)
    result = mlx_whisper.transcribe(
        audio,
        path_or_hf_repo=model,
        language=language,
    )
    return result.get("text", "").strip()
