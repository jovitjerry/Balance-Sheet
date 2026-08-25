"""Module 4 - LLM + RAG.

NOT IMPLEMENTED. Contract only.

The LLM **explains** figures it is handed. It never computes, recomputes, or
estimates them. The accounting equation comes from Module 1 and the ratios from
Module 3, both deterministic Python; this module turns those results into prose
and answers questions about them.

RAG retrieves from the uploaded Balance Sheet's own preserved content before
answering, so responses stay grounded in the document rather than in the
model's priors.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.core.errors import StageNotImplemented
from app.core.schemas import BalanceSheetDocument


class Insight(BaseModel):
    """An explanation, with the document passages it was grounded in."""

    answer: str
    citations: list[str] = []


async def explain(document: BalanceSheetDocument, question: str | None = None) -> Insight:
    """Explain a reviewed Balance Sheet, or answer a question about it.

    :raises StageNotImplemented: always, until Module 4 is built.
    """
    raise StageNotImplemented(
        "The AI insight generator and RAG chatbot are not implemented yet (Module 4)."
    )


__all__ = ["Insight", "explain"]
