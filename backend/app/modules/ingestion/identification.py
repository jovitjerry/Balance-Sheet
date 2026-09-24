from __future__ import annotations
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from app.core.amounts import looks_like_amount, looks_like_year, parse_amount
from app.core.lines import Cell, DocumentLine, build_lines, column_x_for, figure_for
from app.core.schemas import IdentificationEvidence, IdentificationSignal, PeriodCandidate, PeriodSelection, PreliminaryExtraction, SourceRef, UnitHint
from app.core.text import contains, matches_any, normalise
from app.modules.ingestion import anchors
logger = logging.getLogger(__name__)
IDENTIFICATION_THRESHOLD = 6
WEIGHT_TITLE = 5
WEIGHT_OTHER_STATEMENT = -4
WEIGHT_SECTION_HEADER = 2
WEIGHT_TOTAL_LINE = 3
_MONTHS = {'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6, 'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12, 'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12}
_DATE_PATTERN = re.compile('(\\d{1,2})\\s*(?:st|nd|rd|th)?\\s*[-/ ]\\s*([a-z]+)\\s*[-/, ]\\s*((?:19|20)\\d{2})', re.IGNORECASE)
_YEAR_PATTERN = re.compile('(?:19|20)\\d{2}')

def is_balance_sheet(preliminary: PreliminaryExtraction) -> IdentificationEvidence:
    lines = build_lines(preliminary)
    signals: list[IdentificationSignal] = []
    seen: set[str] = set()

    def record(kind: str, text: str, weight: int, source: SourceRef) -> None:
        key = f'{kind}:{normalise(text)}'
        if key in seen:
            return
        seen.add(key)
        signals.append(IdentificationSignal(kind=kind, text=text, weight=weight, source=source))
    for line in lines:
        for segment in line.segments:
            _record_signals_for(segment.label.text, line.source(), record)
    has_title = any((signal.kind == 'title' for signal in signals))
    score = sum((signal.weight for signal in signals if signal.kind != 'other_statement' or not has_title))
    return IdentificationEvidence(is_balance_sheet=score >= IDENTIFICATION_THRESHOLD, score=score, threshold=IDENTIFICATION_THRESHOLD, signals=signals)

def _record_signals_for(label: str, source: SourceRef, record: Callable[[str, str, int, SourceRef], None]) -> None:
    if matches_any(label, anchors.TITLE_PHRASES):
        record('title', label.strip()[:200], WEIGHT_TITLE, source)
    elif (phrase := matches_any(label, anchors.OTHER_STATEMENT_PHRASES)):
        record('other_statement', phrase, WEIGHT_OTHER_STATEMENT, source)
    if anchors.is_combined_total(label):
        record('total_line', label.strip()[:200], WEIGHT_SECTION_HEADER, source)
    elif _total_kind(label):
        record('total_line', label.strip()[:200], WEIGHT_TOTAL_LINE, source)
    if (header := _section_header(label)):
        record('section_header', header, WEIGHT_SECTION_HEADER, source)

def _section_header(label: str) -> str | None:
    normalised = normalise(label)
    for phrases in (anchors.COMBINED_HEADERS, anchors.EQUITY_HEADERS, anchors.ASSETS_HEADERS, anchors.LIABILITIES_HEADERS):
        for phrase in sorted(phrases, key=len, reverse=True):
            candidate = normalise(phrase)
            if normalised == candidate or normalised == f'{candidate} :':
                return phrase
    return None

def _total_kind(label: str) -> str | None:
    if anchors.is_combined_total(label):
        return None
    kind: str | None = None
    if matches_any(label, anchors.TOTAL_ASSETS_PHRASES):
        kind = 'assets'
    elif matches_any(label, anchors.TOTAL_EQUITY_PHRASES):
        kind = 'equity'
    elif matches_any(label, anchors.TOTAL_LIABILITIES_PHRASES):
        kind = 'liabilities'
    if kind is None or anchors.sections_named(label) != {kind}:
        return None
    return kind

def select_period(preliminary: PreliminaryExtraction) -> PeriodSelection | None:
    candidates = _period_candidates(preliminary)
    if not candidates:
        return None
    selected = max(candidates, key=_period_sort_key)
    if len(candidates) == 1:
        reason = 'The document reports a single period.'
    else:
        reason = f'Most recent of {len(candidates)} reporting periods found; the others were recorded but not analysed.'
    return PeriodSelection(selected=selected, candidates=candidates, reason=reason)

def _period_sort_key(candidate: PeriodCandidate) -> tuple:
    return (candidate.end_date or date.min, candidate.year or 0, -(candidate.source.column or 0))

def _period_candidates(preliminary: PreliminaryExtraction) -> list[PeriodCandidate]:
    for line in build_lines(preliminary):
        headings = [cell for cell in line.cells if _period_text(cell.text)]
        if not headings:
            continue
        if any((looks_like_amount(cell.text) and (not looks_like_year(cell.text)) for cell in line.cells)):
            continue
        return [_candidate_from(line, cell) for cell in headings]
    for line in build_lines(preliminary):
        if matches_any(line.label, anchors.TITLE_PHRASES) and _period_text(line.label):
            end_date, year = _parse_period(line.label)
            return [PeriodCandidate(label=line.label.strip()[:200], end_date=end_date, year=year, source=line.source())]
    return []

def _candidate_from(line: DocumentLine, cell: Cell) -> PeriodCandidate:
    end_date, year = _parse_period(cell.text)
    return PeriodCandidate(label=cell.text.strip()[:200], end_date=end_date, year=year, source=line.source(cell.column))

def _period_text(text: str) -> bool:
    return bool(_DATE_PATTERN.search(text) or _YEAR_PATTERN.search(text))

def _parse_period(text: str) -> tuple[date | None, int | None]:
    match = _DATE_PATTERN.search(text)
    if match:
        day, month_name, year = match.groups()
        month = _MONTHS.get(month_name.lower())
        if month:
            try:
                return (date(int(year), month, int(day)), int(year))
            except ValueError:
                logger.info('Ignoring an impossible date in %r', text[:80])
    years = _YEAR_PATTERN.findall(text)
    if years:
        return (None, max((int(year) for year in years)))
    return (None, None)

def detect_units(preliminary: PreliminaryExtraction) -> UnitHint | None:
    currency: str | None = None
    scale_label: str | None = None
    scale_factor: Decimal | None = None
    source: SourceRef | None = None
    for line in build_lines(preliminary):
        text = line.text
        normalised = normalise(text)
        if scale_label is None:
            for phrase, factor in anchors.SCALE_PHRASES.items():
                if contains(normalised, phrase):
                    scale_label = phrase
                    scale_factor = Decimal(factor)
                    source = line.source()
                    break
        if currency is None:
            for symbol, code in anchors.CURRENCY_SYMBOLS.items():
                if symbol in text:
                    currency = code
                    source = source or line.source()
                    break
            else:
                for word in normalised.split():
                    if word in anchors.CURRENCY_WORDS:
                        currency = anchors.CURRENCY_WORDS[word]
                        source = source or line.source()
                        break
        if currency and scale_label:
            break
    if currency is None and scale_label is None:
        return None
    return UnitHint(currency=currency, scale_label=scale_label, scale_factor=scale_factor, source=source)

@dataclass(frozen=True)
class LocatedTotal:
    kind: str
    label: str
    raw: str
    value: Decimal
    source: SourceRef

@dataclass
class LocatedTotals:
    assets: LocatedTotal | None = None
    liabilities: LocatedTotal | None = None
    equity: LocatedTotal | None = None

    @property
    def missing(self) -> list[str]:
        return [name for name in ('assets', 'liabilities', 'equity') if getattr(self, name) is None]

    @property
    def complete(self) -> bool:
        return not self.missing

def locate_totals(preliminary: PreliminaryExtraction, *, period: PeriodSelection | None=None) -> LocatedTotals:
    totals = LocatedTotals()
    lines = build_lines(preliminary)
    column = period.selected.source.column if period else None
    column_x = column_x_for(lines, period)
    for line in lines:
        for segment in line.segments:
            kind = _total_kind(segment.label.text)
            if kind is None:
                continue
            cell = figure_for(segment, column, column_x)
            if cell is None:
                continue
            value = parse_amount(cell.text)
            if value is None:
                continue
            setattr(totals, kind, LocatedTotal(kind=kind, label=segment.label.text.strip()[:200], raw=cell.text.strip(), value=value, source=line.source(cell.column)))
    return totals
__all__ = ['IDENTIFICATION_THRESHOLD', 'LocatedTotal', 'LocatedTotals', 'detect_units', 'is_balance_sheet', 'locate_totals', 'select_period']
