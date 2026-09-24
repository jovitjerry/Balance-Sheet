from __future__ import annotations
import logging
from collections import Counter
from decimal import Decimal
from typing import Any
from app.core.config import Settings, get_settings
from app.core.llm.base import LlmProvider, LlmUnavailable
from app.core.preliminary import load_preliminary
from app.core.schemas import BalanceSheetDocument, BalanceSheetSection, ExtractedBalanceSheet, LineItem, Normalization, NormalizationStatus
from app.core.storage import FileStorage
from app.modules.extraction import taxonomy
from app.modules.extraction.extraction import ExtractedLine, extract_line_items
from app.modules.extraction.normalization import Normalizer
from app.modules.extraction.taxonomy import Section
logger = logging.getLogger(__name__)
NEIGHBOUR_WINDOW = 2
_SECTION_FIELDS: dict[Section, str] = {Section.ASSETS: 'assets', Section.LIABILITIES: 'liabilities', Section.EQUITY: 'equity'}

async def extract(document: BalanceSheetDocument, *, provider: LlmProvider, settings: Settings | None=None, storage: FileStorage | None=None) -> ExtractedBalanceSheet:
    settings = settings or get_settings()
    preliminary = await load_preliminary(document, storage=storage)
    if preliminary is None:
        raise ValueError('The document has no preliminary extraction to work from.')
    if settings.llm_required and (not provider.available()):
        raise LlmUnavailable('The local model service is not reachable, and LLM_REQUIRED is set.')
    lines = extract_line_items(preliminary, period=document.period)
    normalizer = Normalizer(provider=provider, confidence_floor=settings.normalization_confidence_floor)
    currency = document.units.currency if document.units else None
    items: dict[Section, list[LineItem]] = {section: [] for section in Section}
    for index, line in enumerate(lines):
        outcome = await normalizer.normalize(line.label, section=line.section, subsection=line.subsection, neighbours=_neighbours(lines, index), currency=currency)
        items[line.section].append(LineItem(label=line.label, value=line.value, raw=line.raw, subsection=line.subsection.value if line.subsection else None, source=line.source, status=line.status, normalization=Normalization(canonical_label=outcome.canonical_label, status=outcome.status, method=outcome.method, confidence=outcome.confidence, taxonomy_version=outcome.taxonomy_version, model=outcome.model, reason=outcome.reason)))
    return _rebuild(document, items)

def _neighbours(lines: list[ExtractedLine], index: int) -> tuple[str, ...]:
    start = max(0, index - NEIGHBOUR_WINDOW)
    end = min(len(lines), index + NEIGHBOUR_WINDOW + 1)
    return tuple((line.label for position, line in enumerate(lines[start:end], start) if position != index))

def _rebuild(document: BalanceSheetDocument, items: dict[Section, list[LineItem]]) -> ExtractedBalanceSheet:
    existing = document.extracted
    if existing is None:
        raise ValueError('The document has no section totals from Module 1.')
    sections: dict[str, BalanceSheetSection] = {}
    for section, field in _SECTION_FIELDS.items():
        original: BalanceSheetSection = getattr(existing, field)
        lines = items[section]
        sections[field] = original.model_copy(update={'line_items': lines, 'line_items_total': _sum(lines), 'reconciliation_difference': _difference(original.total, lines)})
    return existing.model_copy(update={**sections, 'taxonomy_version': taxonomy.TAXONOMY_VERSION, 'normalization_summary': _summary(items)})

def _sum(items: list[LineItem]) -> Decimal | None:
    values = [item.value for item in items if item.value is not None]
    return sum(values, Decimal(0)) if values else None

def _difference(total: Decimal, items: list[LineItem]) -> Decimal | None:
    extracted = _sum(items)
    return None if extracted is None else total - extracted

def _summary(items: dict[Section, list[LineItem]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for section_items in items.values():
        for item in section_items:
            status = item.normalization.status if item.normalization else NormalizationStatus.UNMAPPED
            counts[status.value] += 1
    return dict(counts)
__all__ = ['NEIGHBOUR_WINDOW', 'extract']
