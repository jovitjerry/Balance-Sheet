"""Module 2 - Full Data Extraction & Normalization.

The whole stage, in order:

    Module 1's preliminary output -> line items (deterministic)
    -> terminology normalization (local model) -> reconciliation -> persist

Two rules govern how this is written.

**The two halves are kept apart.** Extraction answers "what did the document
say?" and runs to completion before a model is consulted about anything. So a
document is fully extracted whether or not Ollama is running, and a
normalization failure can never corrupt a figure - by then the figures are
already fixed.

**Numbers are never the model's business.** Every value here came from
:func:`~app.core.amounts.parse_amount`; the model is shown labels and answers
with a category. It computes nothing, and the accounting equation stays where
it was checked, in Module 1.

Scope: single reporting period. Module 1 selected it; nothing here reads
another column.
"""

from __future__ import annotations

import logging
from collections import Counter
from decimal import Decimal
from typing import Any

from app.core.config import Settings, get_settings
from app.core.llm.base import LlmProvider, LlmUnavailable
from app.core.schemas import (
    BalanceSheetDocument,
    BalanceSheetSection,
    ExtractedBalanceSheet,
    LineItem,
    Normalization,
    NormalizationStatus,
    PreliminaryExtraction,
)
from app.modules.extraction import taxonomy
from app.modules.extraction.extraction import ExtractedLine, extract_line_items
from app.modules.extraction.normalization import Normalizer
from app.modules.extraction.taxonomy import Section

logger = logging.getLogger(__name__)

# How many labels either side of a line are offered as context. A line reads in
# the company of its siblings - "Stock" beside "Trade Debtors" and "Cash at
# bank" is inventory - but a long list dilutes the question rather than
# sharpening it.
NEIGHBOUR_WINDOW = 2

_SECTION_FIELDS: dict[Section, str] = {
    Section.ASSETS: "assets",
    Section.LIABILITIES: "liabilities",
    Section.EQUITY: "equity",
}


async def extract(
    document: BalanceSheetDocument,
    *,
    provider: LlmProvider,
    settings: Settings | None = None,
) -> ExtractedBalanceSheet:
    """Extract and normalise a full Balance Sheet from Module 1's output.

    Consumes only what Module 1 already stored - the preliminary extraction,
    the selected period, the section totals it located - and never re-opens the
    original file.

    :raises LlmUnavailable: only when ``LLM_REQUIRED`` is set. By default an
        unreachable model degrades the terminology step to ``needs_review``
        rather than discarding a complete deterministic extraction.
    """
    settings = settings or get_settings()
    preliminary = document.preliminary
    if preliminary is None:
        raise ValueError("The document has no preliminary extraction to work from.")

    if settings.llm_required and not provider.available():
        raise LlmUnavailable(
            "The local model service is not reachable, and LLM_REQUIRED is set."
        )

    lines = extract_line_items(preliminary, period=document.period)
    normalizer = Normalizer(
        provider=provider,
        confidence_floor=settings.normalization_confidence_floor,
    )
    currency = document.units.currency if document.units else None

    items: dict[Section, list[LineItem]] = {section: [] for section in Section}
    for index, line in enumerate(lines):
        outcome = await normalizer.normalize(
            line.label,
            section=line.section,
            subsection=line.subsection,
            neighbours=_neighbours(lines, index),
            currency=currency,
        )
        items[line.section].append(
            LineItem(
                label=line.label,
                value=line.value,
                raw=line.raw,
                subsection=line.subsection.value if line.subsection else None,
                source=line.source,
                status=line.status,
                normalization=Normalization(
                    canonical_label=outcome.canonical_label,
                    status=outcome.status,
                    method=outcome.method,
                    confidence=outcome.confidence,
                    taxonomy_version=outcome.taxonomy_version,
                    model=outcome.model,
                    reason=outcome.reason,
                ),
            )
        )

    return _rebuild(document, items)


def _neighbours(lines: list[ExtractedLine], index: int) -> tuple[str, ...]:
    """The labels printed around this one, as context for the model."""
    start = max(0, index - NEIGHBOUR_WINDOW)
    end = min(len(lines), index + NEIGHBOUR_WINDOW + 1)
    return tuple(
        line.label for position, line in enumerate(lines[start:end], start) if position != index
    )


def _rebuild(
    document: BalanceSheetDocument, items: dict[Section, list[LineItem]]
) -> ExtractedBalanceSheet:
    """Fill Module 1's section totals in with the line items beneath them.

    Module 1's totals, labels and source references are carried through
    untouched. Module 2 adds line items to them; it does not restate them, and
    it does not re-check the accounting equation - that was decided in Module 1
    on the totals as printed.
    """
    existing = document.extracted
    if existing is None:
        raise ValueError("The document has no section totals from Module 1.")

    sections: dict[str, BalanceSheetSection] = {}
    for section, field in _SECTION_FIELDS.items():
        original: BalanceSheetSection = getattr(existing, field)
        lines = items[section]
        sections[field] = original.model_copy(
            update={
                "line_items": lines,
                "line_items_total": _sum(lines),
                "reconciliation_difference": _difference(original.total, lines),
            }
        )

    return existing.model_copy(
        update={
            **sections,
            "taxonomy_version": taxonomy.TAXONOMY_VERSION,
            "normalization_summary": _summary(items),
        }
    )


def _sum(items: list[LineItem]) -> Decimal | None:
    """The sum of the readable figures, or ``None`` when there are none.

    Unparsed lines are skipped rather than counted as zero: a line nobody could
    read is not a line worth nothing, and treating it as zero would hide the
    gap inside a total that looks complete.
    """
    values = [item.value for item in items if item.value is not None]
    return sum(values, Decimal(0)) if values else None


def _difference(total: Decimal, items: list[LineItem]) -> Decimal | None:
    """How far the extracted lines fall short of the section total.

    **Diagnostic only.** Subtotal lines, rounding and lines whose figure would
    not parse all make exact agreement unusual, so this is recorded for a
    reviewer and never used to reject a document. It is not the accounting
    equation, which Module 1 checked on the printed totals.
    """
    extracted = _sum(items)
    return None if extracted is None else total - extracted


def _summary(items: dict[Section, list[LineItem]]) -> dict[str, int]:
    """Line-item counts by normalization status - how much needs a human."""
    counts: Counter[str] = Counter()
    for section_items in items.values():
        for item in section_items:
            status = (
                item.normalization.status
                if item.normalization
                else NormalizationStatus.UNMAPPED
            )
            counts[status.value] += 1
    return dict(counts)


def preliminary_of(document: BalanceSheetDocument) -> PreliminaryExtraction | None:
    """The preliminary extraction, wherever Module 1 put it."""
    return document.preliminary


__all__ = ["NEIGHBOUR_WINDOW", "extract"]
