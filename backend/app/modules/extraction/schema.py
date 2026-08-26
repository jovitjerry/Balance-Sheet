"""The contract the model's answer must satisfy.

Handed to the provider as a JSON Schema so decoding is *constrained*: Ollama
compiles the schema into a grammar, and an ``enum`` becomes a set of
alternations the sampler cannot leave. An invalid canonical label is therefore
structurally unreachable rather than merely discouraged.

Python validates the answer anyway. A grammar cannot prevent a truncated
response, a provider could be swapped for one that ignores the constraint, and
the section check below is one no grammar could express in the first place.

**Field order is deliberate and load-bearing.** ``reasoning`` comes first so
the model thinks in an unconstrained span and only then commits to the enum.
Constrained decoding is known to cost small models accuracy when they must
reason *inside* a rigid structure; letting them reason first is what avoids
paying that.
"""

from __future__ import annotations

from typing import Any, Sequence

from app.modules.extraction.taxonomy import UNKNOWN

MAX_REASONING_CHARS = 200


def response_schema(allowed: Sequence[str]) -> dict[str, Any]:
    """The JSON Schema for one normalization answer.

    ``allowed`` is the vocabulary legal for this line's section - narrower than
    the whole taxonomy, because the cheapest accuracy available is not offering
    the model a choice that cannot be right.

    :data:`~app.modules.extraction.taxonomy.UNKNOWN` is always offered. A model
    with no way to abstain will always answer, and an answer it had no basis
    for is worse than no answer.
    """
    return {
        "type": "object",
        "properties": {
            "reasoning": {"type": "string", "maxLength": MAX_REASONING_CHARS},
            "canonical_label": {"type": "string", "enum": [*allowed, UNKNOWN]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["reasoning", "canonical_label", "confidence"],
    }


__all__ = ["MAX_REASONING_CHARS", "response_schema"]
