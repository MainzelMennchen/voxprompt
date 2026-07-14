"""Die drei Nachbearbeitungs-Modi (Schritte 5 & 6).

- raw     : kein LLM, Rohtranskript durchreichen.
- cleanup : Transkript bereinigen (prompts/cleanup.md).
- prompt  : aus Gedanken-Dump einen einsatzbereiten Prompt bauen
            (prompts/prompt_builder.md).

Lädt die System-Prompts aus prompts/ und dispatcht den Text über llm.complete().
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from voxprompt.llm import LLMBackend

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


class Mode(str, Enum):
    RAW = "raw"
    CLEANUP = "cleanup"
    PROMPT = "prompt"


class ProcessingPhase(str, Enum):
    """Phasen der Nachbearbeitungspipeline — für UI-Feedback."""

    TRANSCRIBING = "transcribing"
    CLEANING = "cleaning"       # cleanup mode LLM
    PROMPTING = "prompting"     # prompt mode LLM
    RAW_DONE = "raw_done"       # raw mode (kein LLM)


# Welcher System-Prompt gehört zu welchem Modus (raw braucht keinen).
_PROMPT_FILE = {
    Mode.CLEANUP: "cleanup",
    Mode.PROMPT: "prompt_builder",
}


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """Lädt einen System-Prompt aus dem prompts/-Verzeichnis (gecacht)."""
    path = PROMPTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8").strip()


def process(
    mode: Mode,
    transcript: str,
    llm: "LLMBackend",
    *,
    model_override: str | None = None,
    request_overrides: dict | None = None,
) -> str:
    """Wendet den gewählten Modus auf das Transkript an und gibt das Ergebnis zurück.

    raw: gibt das Transkript unverändert zurück (llm wird nicht benutzt).
    cleanup/prompt: schickt das Transkript mit dem passenden System-Prompt durch
    llm.complete(). Ein LLMError wird durchgereicht — der Aufrufer (app.py) zeigt
    daraus eine Menüleisten-Notification.

    model_override: optionaler Modellname für diesen Request (nur endpoint-Backend).
    Wenn None, nutzt das Backend sein Default-Modell.
    request_overrides: optionale per-Modus-Parameter für llm.complete()
    (temperature/max_tokens/timeout — z. B. die Trainings-Parameter des Prompt-Tuners).
    """
    if mode == Mode.RAW:
        return transcript
    system_prompt = load_prompt(_PROMPT_FILE[mode])
    return llm.complete(
        system_prompt, transcript, model=model_override, **(request_overrides or {})
    )
