"""Balance Sheet identification and total-line location for Module 1.

NOT IMPLEMENTED. This is a documented contract only.

MODULE BOUNDARY - read before implementing:

Module 1 locates **total lines only** - Total Assets, Total Liabilities, Total
Shareholders' Equity - and confirms the document is a Balance Sheet at all.
It holds **no general terminology dictionary**.

The full synonym and normalisation vocabulary belongs to Module 2
(``app.modules.extraction.normalization``). When Module 2 exists, the locator
below delegates to it rather than growing its own copy. Do not duplicate
normalisation logic into this module - that duplication is the specific failure
this boundary exists to prevent.
"""

from __future__ import annotations

from app.core.errors import StageNotImplemented
from app.core.schemas import PreliminaryExtraction


def is_balance_sheet(preliminary: PreliminaryExtraction) -> bool:
    """Report whether the parsed document is recognisably a Balance Sheet.

    :raises StageNotImplemented: always, until Module 1 identification is built.
    """
    raise StageNotImplemented(
        "Balance Sheet identification is not implemented yet (Module 1, pending)."
    )


def locate_totals(preliminary: PreliminaryExtraction) -> object:
    """Locate the three section totals needed for the accounting-equation check.

    Deliberately narrow: totals only, no line-item vocabulary.

    :raises StageNotImplemented: always, until Module 1 identification is built.
    """
    raise StageNotImplemented(
        "Total-line location is not implemented yet (Module 1, pending)."
    )


__all__ = ["is_balance_sheet", "locate_totals"]
