"""Tests für den Halluzinations-Guard (Schritt 7)."""

from __future__ import annotations

import pytest

from voxprompt.transcribe import looks_like_hallucination


@pytest.mark.parametrize(
    "text",
    [
        "",
        " ",
        ".",
        "Vielen Dank.",
        "vielen dank",
        "Untertitel der Amara.org-Community",
        "Tschüss!",
        "danke danke danke danke",
        "ja ja ja ja ja ja ja ja",
    ],
)
def test_geistertext_wird_erkannt(text: str) -> None:
    assert looks_like_hallucination(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Ich muss das noch deployen und dann einen commit machen.",
        "Vielen Dank, dass du dir die Pull Request angeschaut hast.",  # 'vielen dank' nur am Anfang, echter Satz
        "Bau mir ein Python-Skript, das Fotos nach Datum sortiert.",
    ],
)
def test_echter_text_bleibt(text: str) -> None:
    assert looks_like_hallucination(text) is False
