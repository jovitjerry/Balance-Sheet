"""Ollama, behind :class:`~app.core.llm.base.LlmProvider`.

The only module in the project that names Ollama. Everything else asks the
Protocol, so swapping the runtime means writing one class - the same
arrangement :class:`~app.modules.ingestion.ocr.OcrEngine` already uses for
Tesseract.

Talking to the HTTP API directly rather than through a framework: it is one
endpoint and one response shape, and a client we own is smaller than the
adapter layer a framework would need to be configured through.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.llm.base import LlmResult, LlmUnavailable

logger = logging.getLogger(__name__)

DEFAULT_HOST = "http://localhost:11434"
# Capped rather than left to the model's default. 8 GB of VRAM is the binding
# constraint on this class of hardware, and the KV cache grows with the context
# window - an uncapped window is what pushes an 8B model into system RAM, where
# it runs an order of magnitude slower.
DEFAULT_NUM_CTX = 4096
DEFAULT_TIMEOUT_S = 120.0
# A dead port should be reported in a moment, not after the full generation
# timeout - this is asked on the happy path, before every document.
_AVAILABILITY_TIMEOUT_S = 2.0


class OllamaProvider:
    """A local model served by Ollama."""

    name = "ollama"

    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        model: str,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        num_ctx: int = DEFAULT_NUM_CTX,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._host = host.rstrip("/")
        self.model = model
        self._timeout_s = timeout_s
        self._num_ctx = num_ctx
        self._transport = transport

    def available(self) -> bool:
        """Whether Ollama answers. Reports rather than raises - it is a question.

        Deliberately does not check that the model is *pulled*: that failure
        has a much better message at the point of use, where it can name the
        model and the setting that chose it.
        """
        return self.installed_models() is not None

    def installed_models(self) -> list[str] | None:
        """The models this server can serve, or ``None`` if it cannot be reached.

        Distinguishing "Ollama is down" from "Ollama is up with nothing pulled"
        matters: they need different things done about them, and a fresh
        install is the second one. A test that needs a model should say which
        of the two stopped it rather than failing on a 404 halfway through.
        """
        try:
            with httpx.Client(
                timeout=_AVAILABILITY_TIMEOUT_S, transport=self._transport
            ) as client:
                response = client.get(f"{self._host}/api/tags")
                if response.status_code != 200:
                    return None
                return [
                    entry.get("name", "")
                    for entry in response.json().get("models", [])
                ]
        except Exception as exc:  # noqa: BLE001 - any failure means unusable
            logger.warning("Ollama is not reachable: %s", exc)
            return None

    async def complete_json(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
        options: dict[str, Any] | None = None,
    ) -> LlmResult:
        """Ask for one JSON answer conforming to ``schema``.

        ``format`` carries the schema, which Ollama compiles into a decoding
        grammar - so the answer matches the shape by construction rather than
        by the model's good behaviour. Validating the *content* is the caller's
        job; this returns whatever parsed.
        """
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": schema,
            # Qwen3 and its relatives reason at length unless told not to,
            # which costs seconds per label for a classification that needs
            # one short sentence. The schema asks for that sentence explicitly.
            "think": False,
            "options": {"num_ctx": self._num_ctx, **(options or {})},
        }

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_s, transport=self._transport
            ) as client:
                response = await client.post(f"{self._host}/api/chat", json=body)
        except httpx.HTTPError as exc:
            raise LlmUnavailable(
                f"Could not reach the local model service at {self._host}."
            ) from exc

        if response.status_code == 404:
            # Ollama is running but this model was never pulled - far and away
            # the commonest first-run failure, so it names the fix.
            raise LlmUnavailable(
                f"The model {self.model!r} is not available locally. Pull it "
                f"with 'ollama pull {self.model}', or set OLLAMA_MODEL to a "
                "model that is installed."
            )
        if response.status_code != 200:
            # The body may carry server paths and internals. Logged, never
            # forwarded - a caller-visible message is one this codebase wrote.
            logger.error(
                "Ollama returned %s: %s", response.status_code, response.text[:500]
            )
            raise LlmUnavailable("The local model service returned an error.")

        content = response.json().get("message", {}).get("content", "")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            # Constrained decoding makes this rare, but a response truncated by
            # the context limit is still possible - and a half-parsed answer
            # would be worse than none.
            raise ValueError("The model did not return valid JSON.") from exc

        return LlmResult(payload=payload, model=self.model, raw=content)


    async def complete_text(
        self, *, prompt: str, options: dict[str, Any] | None = None
    ) -> str:
        """Ask for a plain prose answer, with no schema and no grammar.

        Not on :class:`~app.core.llm.base.LlmProvider`. Module 2 asks only for
        structured answers, and putting this on the Protocol would oblige every
        stub in the test suite to implement a method none of them is asked for.
        It exists here because explaining figures in prose is Module 4's job,
        and the benchmark has to measure a candidate's fitness for that while
        the choice of model is still open.
        """
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": False,
            "options": {"num_ctx": self._num_ctx, **(options or {})},
        }

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_s, transport=self._transport
            ) as client:
                response = await client.post(f"{self._host}/api/chat", json=body)
        except httpx.HTTPError as exc:
            raise LlmUnavailable(
                f"Could not reach the local model service at {self._host}."
            ) from exc

        if response.status_code != 200:
            logger.error(
                "Ollama returned %s: %s", response.status_code, response.text[:500]
            )
            raise LlmUnavailable("The local model service returned an error.")

        return response.json().get("message", {}).get("content", "")


def build_llm_provider(
    *,
    host: str = DEFAULT_HOST,
    model: str,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    num_ctx: int = DEFAULT_NUM_CTX,
) -> OllamaProvider:
    """Construct the configured provider.

    Returns it whether or not Ollama is running, exactly as
    :func:`~app.modules.ingestion.ocr.build_ocr_engine` does: availability is a
    question asked where the model is actually needed, not a reason to refuse
    to start.
    """
    return OllamaProvider(host=host, model=model, timeout_s=timeout_s, num_ctx=num_ctx)


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_NUM_CTX",
    "DEFAULT_TIMEOUT_S",
    "OllamaProvider",
    "build_llm_provider",
]
