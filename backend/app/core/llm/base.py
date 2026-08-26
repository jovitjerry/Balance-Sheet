"""The LLM provider seam.

Modelled on :class:`~app.modules.ingestion.ocr.OcrEngine`, which already works
this way in this codebase: one Protocol, one concrete implementation, and
nothing outside the provider module naming the vendor. Swapping Ollama for
something else means writing one class.

**What a provider is for, and what it is not.** It transports a prompt and a
JSON Schema to a model and brings back parsed JSON. It performs no validation
beyond "this was JSON" - deciding whether the *content* is acceptable belongs
to the module that asked the question, because only that module knows what a
good answer looks like.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.core.errors import BalanceSheetError


class LlmUnavailable(BalanceSheetError):
    """The configured local model cannot be reached.

    Raised only where the caller has said it would rather fail than proceed.
    Module 2's default is the opposite: extraction is deterministic and
    complete without a model, so a missing Ollama degrades the terminology
    mapping to ``needs_review`` instead of discarding a good extraction.
    """

    status_code = 503
    code = "llm_unavailable"


@dataclass(frozen=True)
class LlmResult:
    """One structured answer, and which model produced it.

    ``model`` is carried back rather than assumed by the caller: a stored
    mapping has to name the model that decided it, or re-running the same
    document later cannot say what changed.
    """

    payload: dict[str, Any]
    model: str
    raw: str = ""


@runtime_checkable
class LlmProvider(Protocol):
    """A local model that can answer with JSON matching a supplied schema."""

    name: str
    model: str

    def available(self) -> bool:
        """Whether the model can actually be reached right now."""
        ...

    async def complete_json(
        self,
        *,
        prompt: str,
        schema: dict[str, Any],
        options: dict[str, Any] | None = None,
    ) -> LlmResult:
        """Answer ``prompt`` with JSON conforming to ``schema``.

        Raises on transport failure; the caller decides what that means.
        """
        ...


__all__ = ["LlmProvider", "LlmResult", "LlmUnavailable"]
