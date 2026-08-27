"""The answer contract handed to the model as a JSON Schema.

Ollama compiles a supplied schema into a decoding grammar, so the shape of the
reply is guaranteed by construction rather than by the model's good behaviour -
the same mechanism that makes an invented canonical label unreachable in
Module 2.

**The citation list is the interesting part.** Its ``enum`` is built per request
from the tags actually placed in the context, so *a citation to a source that
was not supplied is structurally impossible*. The model cannot cite page 7 of a
two-page document, and cannot invent a fact tag to hang a claim on. Python
re-validates anyway: a grammar cannot prevent a truncated response, and
resolution can still fail for reasons the grammar knows nothing about.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

# Long enough for a real explanation, short enough that a rambling answer is
# truncated rather than filling the context window. Measured against the Q&A
# benchmark's answers, which run to a few hundred characters when good.
MAX_ANSWER_CHARS = 1200


def answer_schema(citation_ids: Sequence[str]) -> dict[str, Any]:
    """The response schema for one question.

    ``citation_ids`` are the tags available in this context - ``F1``, ``R3``,
    ``C2``. They become a closed ``enum``, which is what makes a fabricated
    citation unreachable rather than merely discouraged.
    """
    return {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "maxLength": MAX_ANSWER_CHARS,
                "description": (
                    "The answer, using only figures given in the context. State "
                    "plainly when the document does not support an answer."
                ),
            },
            "sufficient": {
                "type": "boolean",
                "description": (
                    "False when the supplied context does not contain what the "
                    "question asks for."
                ),
            },
            "citations": _citations(citation_ids),
            "figures_used": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 20,
                "description": (
                    "Every figure stated in the answer, copied exactly as it "
                    "appears in the context."
                ),
            },
        },
        # All four are required so a partial reply is a parse failure rather
        # than an answer with silently missing grounding.
        "required": ["answer", "sufficient", "citations", "figures_used"],
    }


def _citations(citation_ids: Sequence[str]) -> dict[str, Any]:
    """The citations array, closed to the tags in this context.

    With nothing to cite the array is constrained to empty rather than left
    open: an empty ``enum`` is not valid JSON Schema, and an unconstrained
    string array here would be exactly the hole this design exists to close.
    """
    if not citation_ids:
        return {"type": "array", "maxItems": 0, "items": {"type": "string"}}

    return {
        "type": "array",
        "maxItems": 8,
        "items": {"type": "string", "enum": list(dict.fromkeys(citation_ids))},
        "description": "Tags of the context entries this answer relies on.",
    }


__all__ = ["MAX_ANSWER_CHARS", "answer_schema"]
