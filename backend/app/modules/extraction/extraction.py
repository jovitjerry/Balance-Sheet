from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from app.core.amounts import looks_like_amount, parse_amount
from app.core.lines import Cell, DocumentLine, LabelSegment, build_lines, column_x_for, figure_for
from app.core.schemas import ExtractionStatus, PeriodSelection, PreliminaryExtraction, SourceRef
from app.core.text import normalise
from app.modules.extraction.taxonomy import Section, SectionHeader, Subsection, match_header
from app.modules.ingestion.anchors import is_combined_total
_TOTAL_WORDS = frozenset({'total', 'subtotal', 'aggregate'})
_SAME_COLUMN_POINTS = 2.0

@dataclass(frozen=True)
class ExtractedLine:
    label: str
    section: Section
    subsection: Subsection | None
    value: Decimal | None
    raw: str | None
    source: SourceRef
    status: ExtractionStatus

def extract_line_items(preliminary: PreliminaryExtraction, *, period: PeriodSelection | None=None) -> list[ExtractedLine]:
    lines = build_lines(preliminary)
    column = period.selected.source.column if period else None
    column_x = column_x_for(lines, period)
    items: list[ExtractedLine] = []
    headings = _Headings()
    for line in lines:
        for segment in line.segments:
            label = segment.label.text.strip()
            if not label:
                continue
            if is_combined_total(label):
                headings.clear()
                continue
            if (header := match_header(label)):
                headings.opened(segment.label, header)
                continue
            context = headings.governing(segment.label)
            if context is None:
                continue
            if is_total_line(label):
                continue
            item = _line_item(line, segment, context, column, column_x)
            if item is not None:
                items.append(item)
    return items

def _position(cell: Cell) -> tuple[bool, float]:
    if cell.x is not None:
        return (True, cell.x)
    return (False, float(cell.column))

class _Headings:

    def __init__(self) -> None:
        self._bands: list[tuple[bool, float, SectionHeader]] = []

    def clear(self) -> None:
        self._bands.clear()

    def opened(self, cell: Cell, header: SectionHeader) -> None:
        geometric, position = _position(cell)
        tolerance = _SAME_COLUMN_POINTS if geometric else 0.0
        for index, (band_geometric, band_position, _) in enumerate(self._bands):
            if band_geometric is geometric and abs(band_position - position) <= tolerance:
                self._bands[index] = (geometric, band_position, header)
                return
        self._bands.append((geometric, position, header))
        self._bands.sort(key=lambda band: band[1])

    def governing(self, cell: Cell) -> SectionHeader | None:
        if not self._bands:
            return None
        geometric, position = _position(cell)
        candidates = [band for band in self._bands if band[0] is geometric and band[1] <= position + _SAME_COLUMN_POINTS]
        if candidates:
            return candidates[-1][2]
        same_units = [band for band in self._bands if band[0] is geometric]
        return same_units[0][2] if same_units else None

def is_total_line(label: str) -> bool:
    words = normalise(label).split()
    if not words:
        return False
    if words[0] in _TOTAL_WORDS:
        return True
    return len(words) >= 2 and words[0] == 'sub' and (words[1] == 'total')

def _line_item(line: DocumentLine, segment: LabelSegment, context: SectionHeader, column: int | None, column_x: float | None) -> ExtractedLine | None:
    cell = figure_for(segment, column, column_x)
    if cell is not None:
        return ExtractedLine(label=segment.label.text.strip(), section=context.section, subsection=context.subsection, value=parse_amount(cell.text), raw=cell.text.strip(), source=line.source(cell.column), status=ExtractionStatus.EXTRACTED)
    unreadable = _unreadable_figure(line, segment)
    if unreadable is None:
        return None
    return ExtractedLine(label=segment.label.text.strip(), section=context.section, subsection=context.subsection, value=None, raw=unreadable.text.strip(), source=line.source(unreadable.column), status=ExtractionStatus.UNPARSED_VALUE)

def _unreadable_figure(line: DocumentLine, segment: LabelSegment) -> Cell | None:
    cells = line.cells
    for index, cell in enumerate(cells):
        if cell is not segment.label:
            continue
        if index + 1 >= len(cells):
            return None
        candidate = cells[index + 1]
        text = candidate.text.strip()
        if not text or looks_like_amount(text):
            return None
        return candidate if any((character.isdigit() for character in text)) else None
    return None
__all__ = ['ExtractedLine', 'extract_line_items', 'is_total_line']
