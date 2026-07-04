"""Tests für den LLM-Client (Schritt 4).

Deterministisch über httpx.MockTransport — kein laufender Server nötig.
"""

from __future__ import annotations

import httpx
import pytest

from voxprompt.llm import InProcessLLM, LLMClient, LLMError, create_llm


def test_create_llm_waehlt_backend() -> None:
    endpoint = create_llm({"llm": {"llm_backend": "endpoint", "llm_model": "m"}})
    assert isinstance(endpoint, LLMClient)
    endpoint.close()
    # inprocess: nur konstruieren, NICHT das Modell laden
    inproc = create_llm({"llm": {"llm_backend": "inprocess", "llm_model": "m"}})
    assert isinstance(inproc, InProcessLLM)
    assert inproc._model is None  # lazy, noch nichts geladen
    # Default ohne Feld -> endpoint
    assert isinstance(create_llm({"llm": {}}), LLMClient)


def _client(handler, **kwargs) -> LLMClient:
    return LLMClient(
        base_url="http://127.0.0.1:8080/v1",
        model="test-model",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def test_complete_sendet_messages_und_liest_antwort() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.read().decode()
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "  Hallo Welt  "}}]},
        )

    with _client(handler) as client:
        result = client.complete("system-prompt", "user-text")

    assert result == "Hallo Welt"  # getrimmt
    # korrekter Pfad (kein verschluckter /v1)
    assert captured["url"] == "http://127.0.0.1:8080/v1/chat/completions"
    assert "system-prompt" in captured["body"]
    assert "user-text" in captured["body"]
    assert "test-model" in captured["body"]


def test_api_key_setzt_authorization_header() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    with _client(handler, api_key="secret123") as client:
        client.complete("s", "u")

    assert seen["auth"] == "Bearer secret123"


def test_endpoint_nicht_erreichbar_wirft_llmerror() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with _client(handler) as client:
        with pytest.raises(LLMError, match="nicht erreichbar"):
            client.complete("s", "u")


def test_http_500_wirft_llmerror() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with _client(handler) as client:
        with pytest.raises(LLMError, match="500"):
            client.complete("s", "u")


def test_unerwartete_antwort_wirft_llmerror() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    with _client(handler) as client:
        with pytest.raises(LLMError, match="Unerwartete"):
            client.complete("s", "u")
