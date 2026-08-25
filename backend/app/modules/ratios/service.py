"""Module 3 - Deterministic Financial Ratio Engine.

NOT IMPLEMENTED. Contract only.

CONSTRAINT: ratios are computed in deterministic Python and are **never**
delegated to an LLM. ``compute_ratios`` is therefore deliberately synchronous
and pure - no database handle, no LLM client, no I/O of any kind. Keep it that
way: the signature is what makes the constraint structural rather than merely
intended, and it is what makes this module trivially unit-testable.

Planned ratios (Balance Sheet only): Current Ratio, Debt Ratio,
Debt-to-Equity Ratio.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from app.core.errors import StageNotImplemented
from app.core.schemas import ExtractedBalanceSheet


class RatioSet(BaseModel):
    """Computed ratios for one reporting period.

    Each is optional: a ratio whose inputs are absent or whose denominator is
    zero is reported as ``None`` rather than as a fabricated number.
    """

    current_ratio: Decimal | None = None
    debt_ratio: Decimal | None = None
    debt_to_equity: Decimal | None = None
    notes: list[str] = []


def compute_ratios(sheet: ExtractedBalanceSheet) -> RatioSet:
    """Compute Balance Sheet ratios. Pure, synchronous, deterministic.

    :raises StageNotImplemented: always, until Module 3 is built.
    """
    raise StageNotImplemented(
        "The financial ratio engine is not implemented yet (Module 3)."
    )


__all__ = ["RatioSet", "compute_ratios"]
