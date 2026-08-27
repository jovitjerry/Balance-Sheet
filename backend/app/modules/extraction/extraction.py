"""Deterministic line-item extraction: what did the document actually say?

Module 1 located three anchored total lines. This reads **every** line, which
is a harder problem: there is no phrase to search for, only structure - a
label, a figure beside it, and a heading somewhere above that says which part
of the sheet they belong to.

No language model is involved and none may be. A value here is
:func:`~app.core.amounts.parse_amount` applied to printed characters; a section
is the heading the line sits under. Terminology mapping - deciding that "Trade
Debtors" and "Trade Receivables" are one concept - is the *next* step, in
:mod:`app.modules.extraction.normalization`, and is kept separate precisely so
that "what the document said" is never contaminated by "what we think it
meant".

**Single-period scope lives in one call.** Every figure comes from
:func:`~app.core.lines.figure_for`, the same function Module 1 uses to pick its
totals. On a comparative sheet the prior year sits centimetres away and is
equally numeric, so a second implementation here could silently extract the
wrong year and produce a perfectly self-consistent Balance Sheet for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.core.amounts import looks_like_amount, parse_amount
from app.core.lines import (
    Cell,
    DocumentLine,
    LabelSegment,
    build_lines,
    column_x_for,
    figure_for,
)
from app.core.schemas import (
    ExtractionStatus,
    PeriodSelection,
    PreliminaryExtraction,
    SourceRef,
)
from app.core.text import normalise
from app.modules.extraction.taxonomy import Section, SectionHeader, Subsection, match_header

# Reused rather than reimplemented. Recognising the balancing footer is subtle -
# it names two sections and contains the literal text "total liabilities" - and
# Module 1 already had to get it exactly right to avoid reading it as the
# liabilities total. A second implementation here could disagree with that one.
# The dependency runs downstream-on-upstream, which is the direction a pipeline
# runs; Module 1 gains nothing from Module 2 and still imports nothing from it.
from app.modules.ingestion.anchors import is_combined_total

# A line whose first word is one of these summarises the lines above it rather
# than being one of them. Matched as a whole word, never as a prefix: a
# "Totalisator receipts" line is an ordinary receivable, and a prefix test
# would silently delete it.
_TOTAL_WORDS = frozenset({"total", "subtotal", "aggregate"})

# Two headings are in the same column of the page when their left edges are
# within this many points. Labels flush in one column vary by far less than
# that, and two columns of a Balance Sheet are centimetres apart.
_SAME_COLUMN_POINTS = 2.0


@dataclass(frozen=True)
class ExtractedLine:
    """One line of the Balance Sheet, exactly as the document presented it.

    ``label`` and ``raw`` are the document's own words and characters and are
    never rewritten. ``value`` is the parse of ``raw``, and is ``None`` when
    the figure could not be read - the line is kept regardless.
    """

    label: str
    section: Section
    subsection: Subsection | None
    value: Decimal | None
    raw: str | None
    source: SourceRef
    status: ExtractionStatus


def extract_line_items(
    preliminary: PreliminaryExtraction,
    *,
    period: PeriodSelection | None = None,
) -> list[ExtractedLine]:
    """Every line item in the document, for the selected reporting period only.

    Headings set a running context that the lines beneath them inherit, because
    that is how a Balance Sheet is printed: ``ASSETS`` then ``Current Assets``
    then the current assets, until the next heading says otherwise.

    Totals and subtotals are excluded - they summarise the line items rather
    than being any - as are lines above the first heading, which belong to no
    section and are the title and the entity name.
    """
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
                # The balancing footer is the last line of a Balance Sheet by
                # construction - it restates the whole of one side against the
                # other. Whatever follows it is notes, an appendix or a
                # reconciliation summary, and its figures are not line items.
                # Clearing the context rather than stopping outright leaves a
                # second statement further on free to establish its own.
                headings.clear()
                continue

            if header := match_header(label):
                headings.opened(segment.label, header)
                continue

            context = headings.governing(segment.label)
            if context is None:
                # Above the first heading: the title, the entity, the "figures
                # in INR" note. Nothing here belongs to a section, and placing
                # it in one would be an invention.
                continue

            if is_total_line(label):
                continue

            item = _line_item(line, segment, context, column, column_x)
            if item is not None:
                items.append(item)

    return items


def _position(cell: Cell) -> tuple[bool, float]:
    """Where a cell sits across the page, and in what units.

    PDF and OCR pages give a real horizontal position; a worksheet gives an
    ordinal column. They are not interchangeable - two points apart is the same
    column on a page and two columns apart in a spreadsheet - so the unit
    travels with the number.
    """
    if cell.x is not None:
        return True, cell.x
    return False, float(cell.column)


class _Headings:
    """The heading in force for each column of labels on the page.

    A single running context is enough for a Balance Sheet printed as one
    column. It is wrong for the horizontal layout, where ``ASSETS`` heads the
    left of the page and ``LIABILITIES AND EQUITY`` heads the right *on the
    same row*: whichever heading was read second would capture every line that
    followed, and half the sheet would be filed under the wrong section.

    So headings are tracked per column. A line item belongs to the nearest
    heading at or to its left, because a heading is printed flush with its
    column and its items sit level with it or indented under it - never to the
    left of it.
    """

    def __init__(self) -> None:
        self._bands: list[tuple[bool, float, SectionHeader]] = []

    def clear(self) -> None:
        """Forget every heading - the statement they belonged to has ended."""
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
        candidates = [
            band
            for band in self._bands
            if band[0] is geometric and band[1] <= position + _SAME_COLUMN_POINTS
        ]
        if candidates:
            return candidates[-1][2]

        # A label to the left of every heading seen so far. Rare, and the
        # left-most heading is the only defensible reading of it.
        same_units = [band for band in self._bands if band[0] is geometric]
        return same_units[0][2] if same_units else None


def is_total_line(label: str) -> bool:
    """Whether this label announces a total rather than a line item.

    Module 1 locates the three grand totals by name; the subtotals between them
    - ``Total Current Assets``, ``Total Non-Current Liabilities`` - are known to
    nothing else, so leaving them out is Module 2's job. Including them would
    double a section and make the reconciliation against Module 1's total
    meaningless.

    Public because Module 3 re-applies it as a guard. Every figure Module 3 sums
    came through the exclusion above, so a total reaching an aggregate would
    mean this test had regressed - and Module 3 would inflate a section
    silently. It asserts rather than trusts, using this function rather than a
    second copy of the rule, because two copies could disagree and only one of
    them would be the one that ran here.
    """
    words = normalise(label).split()
    if not words:
        return False
    if words[0] in _TOTAL_WORDS:
        return True
    return len(words) >= 2 and words[0] == "sub" and words[1] == "total"


def _line_item(
    line: DocumentLine,
    segment: LabelSegment,
    context: SectionHeader,
    column: int | None,
    column_x: float | None,
) -> ExtractedLine | None:
    """Build one line item, or ``None`` if this segment carries no figure."""
    cell = figure_for(segment, column, column_x)
    if cell is not None:
        return ExtractedLine(
            label=segment.label.text.strip(),
            section=context.section,
            subsection=context.subsection,
            value=parse_amount(cell.text),
            raw=cell.text.strip(),
            source=line.source(cell.column),
            status=ExtractionStatus.EXTRACTED,
        )

    unreadable = _unreadable_figure(line, segment)
    if unreadable is None:
        return None

    return ExtractedLine(
        label=segment.label.text.strip(),
        section=context.section,
        subsection=context.subsection,
        value=None,
        raw=unreadable.text.strip(),
        source=line.source(unreadable.column),
        status=ExtractionStatus.UNPARSED_VALUE,
    )


def _unreadable_figure(line: DocumentLine, segment: LabelSegment) -> Cell | None:
    """The cell beside this label that was meant to be a figure but would not parse.

    Deliberately narrow. The cell has to contain a digit before it is treated
    as an attempted figure, because on a horizontal sheet the cell to the right
    of a label is routinely *another label* - and reading "Total Current
    Liabilities" as an unreadable amount would invent a line item that does not
    exist.
    """
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
        return candidate if any(character.isdigit() for character in text) else None
    return None  # pragma: no cover - the label always comes from this line


__all__ = ["ExtractedLine", "extract_line_items", "is_total_line"]
