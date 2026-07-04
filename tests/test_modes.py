"""Tests für die Modus-Verdrahtung (Schritt 5/6).

Nutzt ein Fake-LLM — kein Server nötig. Prüft, dass der richtige System-Prompt
geladen und der Transkript-Text durchgereicht wird.
"""

from __future__ import annotations

from voxprompt.modes import Mode, load_prompt, process


class FakeLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_text: str) -> str:
        self.calls.append((system_prompt, user_text))
        return self.reply


def test_load_prompt_cleanup() -> None:
    assert "Transkript-Korrektor" in load_prompt("cleanup")


def test_raw_reicht_unveraendert_durch_ohne_llm() -> None:
    llm = FakeLLM("sollte nicht benutzt werden")
    assert process(Mode.RAW, "hallo welt", llm) == "hallo welt"
    assert llm.calls == []  # raw ruft das LLM nicht auf


def test_cleanup_nutzt_cleanup_prompt_und_llm() -> None:
    cleaned = "Ich muss das noch deployen und dann einen commit machen."
    llm = FakeLLM(cleaned)
    messy = "ähm ich muss das noch deployen und dann ein commit machen"
    out = process(Mode.CLEANUP, messy, llm)

    assert out == cleaned
    system_prompt, user_text = llm.calls[0]
    assert "Transkript-Korrektor" in system_prompt  # cleanup.md geladen
    assert user_text == messy  # Transkript unverändert weitergereicht


def test_prompt_mode_nutzt_prompt_builder() -> None:
    llm = FakeLLM("egal")
    process(Mode.PROMPT, "mach mir einen plan", llm)
    system_prompt, _ = llm.calls[0]
    assert "Prompt-Engineering" in system_prompt  # prompt_builder.md geladen
