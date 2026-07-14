"""Tests für die Modus-Verdrahtung (Schritt 5/6).

Nutzt ein Fake-LLM — kein Server nötig. Prüft, dass der richtige System-Prompt
geladen und der Transkript-Text durchgereicht wird.
"""

from __future__ import annotations

from voxprompt.modes import Mode, load_prompt, process


class FakeLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[tuple[str, str, str | None]] = []
        self.kwargs: list[dict] = []

    def complete(
        self, system_prompt: str, user_text: str, *, model: str | None = None, **kwargs
    ) -> str:
        self.calls.append((system_prompt, user_text, model))
        self.kwargs.append(kwargs)
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
    system_prompt, user_text, _model = llm.calls[0]
    assert "Transkript-Korrektor" in system_prompt  # cleanup.md geladen
    assert user_text == messy  # Transkript unverändert weitergereicht


# Das exakte System-Prompt aus dem prompt-tuner-8b-Training — jede Abweichung
# kostet messbar Qualität. Dieser Test schützt vor versehentlichen Änderungen.
PROMPT_TUNER_SYSTEM = (
    "Du bist ein Prompt-Optimierer. Wandle rohe, diktierte Eingaben in präzise, "
    "strukturierte Prompts um. Behalte die Sprache des Nutzers bei, entferne "
    "Füllwörter, ergänze sinnvolle Struktur und Output-Anforderungen. "
    "Erfinde keine Fakten, die nicht im Input stehen."
)


def test_prompt_mode_nutzt_exaktes_trainings_prompt() -> None:
    llm = FakeLLM("egal")
    process(Mode.PROMPT, "mach mir einen plan", llm)
    system_prompt, _, _model = llm.calls[0]
    assert system_prompt == PROMPT_TUNER_SYSTEM  # prompt_builder.md byte-genau


def test_model_override_wird_durchgereicht() -> None:
    """Per-Modus Modell-Override landet im LLM-Aufruf."""
    llm = FakeLLM("bereinigt")
    process(Mode.CLEANUP, "hallo", llm, model_override="special-model")
    _, _, model = llm.calls[0]
    assert model == "special-model"


def test_model_override_none_ohne_parameter() -> None:
    """Ohne Override ist model=None (Backend nutzt sein Default)."""
    llm = FakeLLM("bereinigt")
    process(Mode.CLEANUP, "hallo", llm)
    _, _, model = llm.calls[0]
    assert model is None


def test_raw_ignoriert_model_override() -> None:
    """Raw-Modus ruft LLM nicht auf — Override ist irrelevant."""
    llm = FakeLLM("sollte nicht kommen")
    result = process(Mode.RAW, "rohtext", llm, model_override="irrelevant")
    assert result == "rohtext"
    assert llm.calls == []


def test_request_overrides_werden_durchgereicht() -> None:
    """Per-Modus Request-Parameter (temperature/max_tokens/timeout) erreichen complete()."""
    llm = FakeLLM("optimiert")
    overrides = {"temperature": 0.2, "max_tokens": 800, "timeout": 30}
    process(Mode.PROMPT, "dump", llm, request_overrides=overrides)
    assert llm.kwargs[0] == overrides


def test_request_overrides_none_ist_leer() -> None:
    """Ohne Overrides bekommt complete() keine Extra-Parameter."""
    llm = FakeLLM("x")
    process(Mode.CLEANUP, "hallo", llm)
    assert llm.kwargs[0] == {}


# --- Sprachvarianten für cleanup ---

def test_load_prompt_cleanup_en_lädt_englischen_prompt() -> None:
    prompt = load_prompt("cleanup_en")
    assert "transcript corrector" in prompt.lower()
    # Englisches Füllwort im Prompt enthalten?
    assert any(word in prompt.lower() for word in ("um", "uh", "like", "you know"))


def test_cleanup_wählt_prompt_nach_sprache() -> None:
    """Cleanup wählt cleanup.md vs cleanup_en.md abhängig von language."""
    llm = FakeLLM("bereinigt")
    process(Mode.CLEANUP, "hallo welt", llm, language="de")
    system_de, _, _ = llm.calls[0]

    llm2 = FakeLLM("cleaned")
    process(Mode.CLEANUP, "hello world", llm2, language="en")
    system_en, _, _ = llm2.calls[0]

    assert system_de != system_en  # unterschiedliche Prompts
    assert "Transkript-Korrektor" in system_de
    # cleanup_en.md muss englischen Inhalt haben


def test_raw_ignoriert_language_parameter() -> None:
    """Raw-Modus ruft LLM nicht auf — language ist irrelevant."""
    llm = FakeLLM("sollte nicht kommen")
    result = process(Mode.RAW, "rohtext", llm, language="en")
    assert result == "rohtext"
    assert llm.calls == []
