"""Module 2 - Full Data Extraction & Normalization.

NOT IMPLEMENTED. Contract only.

This module owns **complete** line-item extraction and **all** terminology
normalisation - mapping the many ways a Balance Sheet can name the same concept
onto one standard structure. That vocabulary lives here and nowhere else;
Module 1 must not grow its own copy.

Scope: single reporting period. No year-over-year comparison.
"""

from __future__ import annotations

from app.core.errors import StageNotImplemented
from app.core.schemas import BalanceSheetDocument, ExtractedBalanceSheet


async def extract(document: BalanceSheetDocument) -> ExtractedBalanceSheet:
    """Extract and normalise a full Balance Sheet from preliminary output.

    Reads ``document.preliminary`` - raw text and tables preserved by Module 1
    - and returns a normalised, single-period structure.

    :raises StageNotImplemented: always, until Module 2 is built.
    """
    raise StageNotImplemented(
        "Full data extraction and normalization are not implemented yet (Module 2)."
    )


__all__ = ["extract"]
