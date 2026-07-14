"""LLM-Backends für die Nachbearbeitung (Schritt 4 + Phase 2/1).

Zwei umschaltbare Backends mit identischem `complete(system_prompt, user_text)`:
- `LLMClient` ("endpoint"): OpenAI-kompatibler HTTP-Client (lokaler MLX-Server).
  Für die eigene Entwicklung — braucht einen laufenden Server.
- `InProcessLLM` ("inprocess"): lädt das Modell über die mlx_lm-Python-API direkt
  in den Prozess (kein HTTP, kein Server). Für die verteilbare App.

`create_llm(config)` wählt anhand von `[llm] llm_backend` aus. `modes.py` sieht nur
das gemeinsame `LLMBackend`-Protokoll und merkt nichts vom konkreten Backend.
"""

from __future__ import annotations

import gc
import re
from typing import Protocol, runtime_checkable

import httpx

# Inline-Thinking-Block (manche Modelle schreiben <think>…</think> in content).
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class LLMError(Exception):
    """Klartext-Fehler aus der LLM-Stufe — geeignet für eine Menüleisten-Notification."""


@runtime_checkable
class LLMBackend(Protocol):
    """Gemeinsame Schnittstelle beider Backends (was modes.py braucht)."""

    def complete(
        self,
        system_prompt: str,
        user_text: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> str: ...

    def close(self) -> None: ...


class LLMClient:
    """Client für /chat/completions auf einem OpenAI-kompatiblen Endpoint.

    base_url/model/api_key sind bewusst Konstruktor-Parameter, damit sich das Ziel
    (lokaler MLX-Server vs. anderer Anbieter) leicht umschalten lässt.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_seconds: int = 60,
        max_tokens: int = 2000,
        disable_thinking: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.disable_thinking = disable_thinking
        self._endpoint = f"{self.base_url}/chat/completions"

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        # Vollständige URL wird pro Request gesetzt (kein base_url-Join -> keine
        # Überraschungen mit dem /v1-Pfad). transport ist v. a. für Tests gedacht.
        self._client = httpx.Client(
            timeout=timeout_seconds,
            headers=headers,
            transport=transport,
        )

    @classmethod
    def from_config(cls, config: dict) -> "LLMClient":
        """Baut den Client aus dem [llm]-Abschnitt der config.toml."""
        llm = config.get("llm", {})
        return cls(
            base_url=llm.get("llm_endpoint", "http://127.0.0.1:8080/v1"),
            model=llm.get("llm_model", ""),
            api_key=llm.get("api_key", ""),
            timeout_seconds=llm.get("timeout_seconds", 60),
            max_tokens=llm.get("max_tokens", 2000),
            disable_thinking=llm.get("disable_thinking", True),
        )

    def complete(
        self,
        system_prompt: str,
        user_text: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> str:
        """Schickt System- + User-Message und gibt den Antworttext zurück.

        Die optionalen Parameter überschreiben die Konstruktor-Defaults für diesen
        einen Request (per-Modus Overrides): `model` das Modell, `temperature` die
        Sampling-Temperatur (ohne Angabe entscheidet der Server), `max_tokens` das
        Antwort-Budget, `timeout` die Wartezeit in Sekunden.

        Wirft bei jedem Problem (Endpoint nicht erreichbar, Timeout, HTTP-Fehler,
        unerwartete Antwort) ein LLMError mit klarer Meldung — kein stiller Absturz.
        """
        payload = {
            "model": model or self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "stream": False,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if self.disable_thinking:
            # Reasoning-/Thinking-Modelle (z. B. Qwen3.x) verbrauchen sonst das ganze
            # Token-Budget fürs Denken und liefern leeren content. Schaltet das Denken
            # ab (von mlx_lm / Qwen unterstützt; andere Server ignorieren das Feld).
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        effective_timeout = timeout if timeout is not None else self.timeout_seconds
        try:
            response = self._client.post(
                self._endpoint, json=payload, timeout=effective_timeout
            )
            response.raise_for_status()
        except httpx.ConnectError as exc:
            raise LLMError(
                f"LLM-Endpoint nicht erreichbar ({self.base_url}). Läuft der Server?"
            ) from exc
        except httpx.TimeoutException as exc:
            raise LLMError(
                f"LLM-Zeitüberschreitung nach {effective_timeout}s ({self.base_url})."
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip()[:200]
            raise LLMError(
                f"LLM-Fehler {exc.response.status_code}: {detail or 'keine Details'}"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM-Anfrage fehlgeschlagen: {exc}") from exc

        try:
            data = response.json()
            choice = data["choices"][0]
            content = choice["message"].get("content") or ""
            finish_reason = choice.get("finish_reason")
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError(
                f"Unerwartete LLM-Antwort: {response.text.strip()[:200]}"
            ) from exc

        content = _THINK_BLOCK.sub("", content).strip()
        if not content:
            # Typisch bei Reasoning-Modellen: das Token-Budget ging fürs Denken drauf.
            hint = (
                " (max_tokens erschöpft — erhöhen oder disable_thinking=true setzen)"
                if finish_reason == "length"
                else ""
            )
            raise LLMError(f"LLM lieferte keinen Text{hint}.")
        return content

    def close(self) -> None:
        """Schließt den zugrunde liegenden HTTP-Client."""
        self._client.close()

    def __enter__(self) -> "LLMClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class InProcessLLM:
    """LLM-Backend ohne Server: lädt Modelle über mlx_lm direkt in den Prozess.

    Es ist immer genau EIN Modell im Speicher (lazy beim ersten `complete()`
    geladen, App-Start bleibt schnell). Fordert ein Aufruf per `model`-Override
    ein anderes Modell an (per-Modus-Modelle), wird das aktuelle entladen und
    das angeforderte geladen — ein Moduswechsel kostet damit einmalig die
    Ladezeit (~10 s bei 9B-4bit), hält den RAM-Bedarf aber bei einem Modell.
    """

    def __init__(
        self,
        model: str,
        max_tokens: int = 2000,
        disable_thinking: bool = True,
    ) -> None:
        self.model_id = model
        self.max_tokens = max_tokens
        self.disable_thinking = disable_thinking
        self._model = None
        self._tokenizer = None
        self._loaded_id: str | None = None

    @classmethod
    def from_config(cls, config: dict) -> "InProcessLLM":
        """Baut das Backend aus dem [llm]-Abschnitt der config.toml."""
        llm = config.get("llm", {})
        return cls(
            model=llm.get("llm_model", ""),
            max_tokens=llm.get("max_tokens", 2000),
            disable_thinking=llm.get("disable_thinking", True),
        )

    def _ensure_loaded(self, model_id: str) -> None:
        """Stellt sicher, dass genau `model_id` geladen ist (entlädt ggf. das alte)."""
        if self._model is not None and self._loaded_id == model_id:
            return
        if self._model is not None:
            print(
                f"[voxprompt] Modellwechsel: entlade {self._loaded_id}, lade {model_id} …",
                flush=True,
            )
            self._unload()
        from mlx_lm import load  # Import hier, damit der App-Start nicht wartet

        self._model, self._tokenizer = load(model_id)
        self._loaded_id = model_id

    def _unload(self) -> None:
        """Gibt das aktuell geladene Modell frei (inkl. Metal-Buffer)."""
        self._model = None
        self._tokenizer = None
        self._loaded_id = None
        gc.collect()
        try:
            import mlx.core as mx

            mx.clear_cache()  # gibt die Metal-Buffer wirklich ans System zurück
        except Exception:
            pass

    def complete(
        self,
        system_prompt: str,
        user_text: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> str:
        """Erzeugt die Antwort lokal über mlx_lm — identische Semantik wie LLMClient.

        `model` wählt das Modell für diesen Aufruf (per-Modus-Modelle): weicht es
        vom aktuell geladenen ab, wird gewechselt (entladen + laden, ~10 s).
        Ohne Angabe läuft self.model_id. `max_tokens` überschreibt das Budget;
        `temperature` und `timeout` werden ignoriert (mlx_lm-Default-Sampler,
        synchrone Generierung).
        """
        from mlx_lm import generate

        try:
            self._ensure_loaded(model or self.model_id)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ]
            template_kwargs = {}
            if self.disable_thinking:
                # Spiegelt chat_template_kwargs.enable_thinking=false des HTTP-Backends.
                template_kwargs["enable_thinking"] = False
            prompt = self._tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=False,
                **template_kwargs,
            )
            output = generate(
                self._model,
                self._tokenizer,
                prompt=prompt,
                max_tokens=max_tokens or self.max_tokens,
                verbose=False,
            )
        except Exception as exc:
            raise LLMError(f"In-Process-LLM fehlgeschlagen: {exc}") from exc

        content = _THINK_BLOCK.sub("", output or "").strip()
        if not content:
            raise LLMError("In-Process-LLM lieferte keinen Text.")
        return content

    def close(self) -> None:
        """Gibt das geladene Modell frei (für die nächste Session neu laden)."""
        self._unload()


def create_llm(config: dict) -> LLMBackend:
    """Wählt das Backend anhand von [llm] llm_backend ("endpoint" | "inprocess")."""
    backend = config.get("llm", {}).get("llm_backend", "endpoint")
    if backend == "inprocess":
        return InProcessLLM.from_config(config)
    return LLMClient.from_config(config)
