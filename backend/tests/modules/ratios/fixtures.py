"""Building an ExtractedBalanceSheet by hand, for tests that need a shape.

Module 3 consumes a finished data structure, so unlike Modules 1 and 2 it can
be tested against sheets assembled directly - which is what makes negative
equity, a zero denominator and a duplicated canonical label reachable at all.
The real documents are exercised separately in ``test_real_document.py``.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.schemas import (
    BalanceSheetSection,
    ExtractedBalanceSheet,
    ExtractionStatus,
    LineItem,
    Normalization,
    NormalizationMethod,
    NormalizationStatus,
    SourceRef,
)
from app.modules.extraction.taxonomy import TAXONOMY_VERSION


def item(
    label: str,
    value: str | None,
    canonical: str | None,
    *,
    status: NormalizationStatus = NormalizationStatus.NORMALIZED,
    subsection: str | None = None,
    row: int = 0,
    extraction: ExtractionStatus = ExtractionStatus.EXTRACTED,
) -> LineItem:
    """One line item, normalized or not.

    Passing ``canonical=None`` builds the shape Module 2 produces when nobody
    could map the label: the line, its figure and its source are all intact and
    only the category is missing.
    """
    return LineItem(
        label=label,
        value=Decimal(value) if value is not None else None,
        raw=value,
        subsection=subsection,
        source=SourceRef(page_index=0, row=row, column=1),
        status=extraction,
        normalization=Normalization(
            canonical_label=canonical,
            status=status if canonical else NormalizationStatus.NEEDS_REVIEW,
            method=NormalizationMethod.LLM if canonical else NormalizationMethod.UNAVAILABLE,
            confidence=0.95 if canonical else None,
            taxonomy_version=TAXONOMY_VERSION,
            model="test-model",
            reason=None if canonical else "model_abstained",
        ),
    )


def section(total: str, items: list[LineItem], label: str = "Total") -> BalanceSheetSection:
    values = [entry.value for entry in items if entry.value is not None]
    line_items_total = sum(values, Decimal(0)) if values else None
    return BalanceSheetSection(
        total=Decimal(total),
        total_label=label,
        total_raw=total,
        total_source=SourceRef(page_index=0, row=99, column=1),
        line_items=items,
        line_items_total=line_items_total,
        reconciliation_difference=(
            Decimal(total) - line_items_total if line_items_total is not None else None
        ),
    )


def sheet(
    *,
    assets: BalanceSheetSection,
    liabilities: BalanceSheetSection,
    equity: BalanceSheetSection,
    currency: str | None = "INR",
    taxonomy_version: str | None = TAXONOMY_VERSION,
) -> ExtractedBalanceSheet:
    return ExtractedBalanceSheet(
        entity_name="Test Company Limited",
        period_label="As at 31 March 2026",
        currency=currency,
        assets=assets,
        liabilities=liabilities,
        equity=equity,
        taxonomy_version=taxonomy_version,
    )


def balanced_sheet() -> ExtractedBalanceSheet:
    """A complete, fully normalized sheet. The arithmetic below is checkable by hand.

    Current assets   850,000 = 125,000 + 280,000 + 350,000 +  95,000
    Non-current      1,450,000 = 1,200,000 + 150,000 + 100,000
    Total assets     2,300,000
    Current liabs      650,000 = 300,000 + 200,000 + 150,000
    Non-current        700,000 = 600,000 + 100,000
    Total liabs      1,350,000
    Equity             950,000 = 600,000 + 350,000
    """
    return sheet(
        assets=section(
            "2300000",
            [
                item("Cash and cash equivalents", "125000", "cash_and_cash_equivalents",
                     subsection="current", row=1),
                item("Trade receivables", "280000", "trade_receivables",
                     subsection="current", row=2),
                item("Inventory", "350000", "inventory", subsection="current", row=3),
                item("Other current assets", "95000", "other_current_assets",
                     subsection="current", row=4),
                item("Property, plant and equipment", "1200000",
                     "property_plant_and_equipment", subsection="non_current", row=5),
                item("Intangible assets", "150000", "intangible_assets",
                     subsection="non_current", row=6),
                item("Other non-current assets", "100000", "other_non_current_assets",
                     subsection="non_current", row=7),
            ],
            label="TOTAL ASSETS",
        ),
        liabilities=section(
            "1350000",
            [
                item("Trade payables", "300000", "trade_payables",
                     subsection="current", row=8),
                item("Short-term borrowings", "200000", "short_term_borrowings",
                     subsection="current", row=9),
                item("Other current liabilities", "150000", "other_current_liabilities",
                     subsection="current", row=10),
                item("Long-term borrowings", "600000", "long_term_borrowings",
                     subsection="non_current", row=11),
                item("Other non-current liabilities", "100000",
                     "other_non_current_liabilities", subsection="non_current", row=12),
            ],
            label="Total Liabilities",
        ),
        equity=section(
            "950000",
            [
                item("Share capital", "600000", "share_capital", row=13),
                item("Retained earnings", "350000", "retained_earnings", row=14),
            ],
            label="Total Equity",
        ),
    )


__all__ = ["balanced_sheet", "item", "section", "sheet"]
