"""Balance Sheet identification and total-line location for Module 1.

MODULE BOUNDARY - read before implementing:

Module 1 locates **total lines only** - Total Assets, Total Liabilities, Total
Shareholders' Equity - and confirms the document is a Balance Sheet at all.
It holds **no general terminology dictionary**; the narrow phrase set it is
allowed to know lives in :mod:`app.modules.ingestion.anchors` and is guarded by
the note at the top of that file.

The full synonym and normalisation vocabulary belongs to Module 2
(``app.modules.extraction.normalization``). When Module 2 exists, the locator
below delegates to it rather than growing its own copy. Do not duplicate
normalisation logic into this module - that duplication is the specific failure
this boundary exists to prevent.

Everything here is deterministic Python. No language model is consulted, asked
to judge, or given a figure to check. A Balance Sheet either balances or it
does not, and that is arithmetic.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.core.amounts import looks_like_amount, looks_like_year, parse_amount
from app.core.lines import (
    Cell,
    DocumentLine,
    build_lines,
    column_x_for,
    figure_for,
)
from app.core.schemas import (
    IdentificationEvidence,
    IdentificationSignal,
    PeriodCandidate,
    PeriodSelection,
    PreliminaryExtraction,
    SourceRef,
    UnitHint,
)
from app.core.text import contains, matches_any, normalise
from app.modules.ingestion import anchors

logger = logging.getLogger(__name__)

# A document scoring at or above this is a Balance Sheet. Reaching it needs
# more than one kind of evidence: a title alone (5) does not, and neither does
# a lone total line (3). A title plus one located total does, and so do the
# three section headers together - which is the case that matters for a page
# whose title sits on a cover sheet.
IDENTIFICATION_THRESHOLD = 6

WEIGHT_TITLE = 5
WEIGHT_OTHER_STATEMENT = -4
WEIGHT_SECTION_HEADER = 2
WEIGHT_TOTAL_LINE = 3

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_DATE_PATTERN = re.compile(
    r"(\d{1,2})\s*(?:st|nd|rd|th)?\s*[-/ ]\s*([a-z]+)\s*[-/, ]\s*((?:19|20)\d{2})",
    re.IGNORECASE,
)
_YEAR_PATTERN = re.compile(r"(?:19|20)\d{2}")


# --------------------------------------------------------------------------
# Identification
# --------------------------------------------------------------------------


def is_balance_sheet(preliminary: PreliminaryExtraction) -> IdentificationEvidence:
    """Decide whether the parsed document is a Balance Sheet, with reasons.

    Returns the evidence rather than a bare boolean so a rejection can be
    argued with. "Not a Balance Sheet" on its own is not an auditable verdict;
    a caller - and later a human - needs to see which signals were found and
    which were missing.
    """
    lines = build_lines(preliminary)
    signals: list[IdentificationSignal] = []
    seen: set[str] = set()

    def record(kind: str, text: str, weight: int, source: SourceRef) -> None:
        key = f"{kind}:{normalise(text)}"
        if key in seen:
            return
        seen.add(key)
        signals.append(
            IdentificationSignal(kind=kind, text=text, weight=weight, source=source)
        )

    # Every label on the row, not just the leading one. A horizontal sheet
    # heads its right-hand column "LIABILITIES AND EQUITY" and prints its
    # liabilities and equity totals there; reading only cell zero would discard
    # that evidence. Two different notions of "this row's label" inside one
    # module is what let the horizontal layout go unnoticed, so identification
    # and total location now share this one.
    for line in lines:
        for segment in line.segments:
            _record_signals_for(segment.label.text, line.source(), record)

    has_title = any(signal.kind == "title" for signal in signals)
    score = sum(
        signal.weight
        for signal in signals
        if signal.kind != "other_statement" or not has_title
    )

    return IdentificationEvidence(
        is_balance_sheet=score >= IDENTIFICATION_THRESHOLD,
        score=score,
        threshold=IDENTIFICATION_THRESHOLD,
        signals=signals,
    )


def _record_signals_for(
    label: str,
    source: SourceRef,
    record: Callable[[str, str, int, SourceRef], None],
) -> None:
    """Score one label and hand whatever it evidences to ``record``."""
    if matches_any(label, anchors.TITLE_PHRASES):
        record("title", label.strip()[:200], WEIGHT_TITLE, source)
    elif phrase := matches_any(label, anchors.OTHER_STATEMENT_PHRASES):
        # Only counted when no Balance Sheet title was found: an annual report
        # legitimately contains all of these statements, and the presence of a
        # Cash Flow Statement says nothing against the Balance Sheet printed
        # three pages earlier.
        record("other_statement", phrase, WEIGHT_OTHER_STATEMENT, source)

    if anchors.is_combined_total(label):
        # The balancing footer. Evidence of a Balance Sheet, but never a
        # section total - see the note in anchors.py.
        record("total_line", label.strip()[:200], WEIGHT_SECTION_HEADER, source)
    elif _total_kind(label):
        record("total_line", label.strip()[:200], WEIGHT_TOTAL_LINE, source)

    if header := _section_header(label):
        record("section_header", header, WEIGHT_SECTION_HEADER, source)


def _section_header(label: str) -> str | None:
    """Recognise a bare section heading, not a line that merely mentions one.

    ``ASSETS`` on its own line is a heading. ``Total assets`` is not, and
    neither is ``Assets pledged as security``, so the whole label has to be the
    heading rather than contain it.
    """
    normalised = normalise(label)
    for phrases in (
        anchors.COMBINED_HEADERS,
        anchors.EQUITY_HEADERS,
        anchors.ASSETS_HEADERS,
        anchors.LIABILITIES_HEADERS,
    ):
        for phrase in sorted(phrases, key=len, reverse=True):
            candidate = normalise(phrase)
            if normalised == candidate or normalised == f"{candidate} :":
                return phrase
    return None


def _total_kind(label: str) -> str | None:
    """Which section total this line is, if any.

    The combined balancing footer is ruled out **first**. It contains the
    literal text "total liabilities", so any order that checks the section
    totals before it would read the footer as the liabilities total and inflate
    liabilities by the entire equity balance.

    The phrase match is then required to agree with the sections the label
    actually names. Two mechanisms decide the same question here - a phrase
    lookup and a structural section count - and this is what stops them
    disagreeing silently: a label that names more than one section, or names a
    different one from the phrase that matched it, yields no total at all.
    Refusing is safe; guessing is what produced the defect this guard closes.
    """
    if anchors.is_combined_total(label):
        return None

    kind: str | None = None
    if matches_any(label, anchors.TOTAL_ASSETS_PHRASES):
        kind = "assets"
    elif matches_any(label, anchors.TOTAL_EQUITY_PHRASES):
        kind = "equity"
    elif matches_any(label, anchors.TOTAL_LIABILITIES_PHRASES):
        kind = "liabilities"

    if kind is None or anchors.sections_named(label) != {kind}:
        return None
    return kind


# --------------------------------------------------------------------------
# Reporting period
# --------------------------------------------------------------------------


def select_period(preliminary: PreliminaryExtraction) -> PeriodSelection | None:
    """Choose the one reporting period to analyse.

    **Single-period scope.** A comparative Balance Sheet prints two or more
    columns; the most recent is selected and the others are recorded but never
    read. This is not a year-over-year comparison and must not become one - no
    figure from a non-selected column is used for anything.

    Returns ``None`` when the document names no period at all, which is not an
    error: an un-dated sheet still has one column of figures to check.
    """
    candidates = _period_candidates(preliminary)
    if not candidates:
        return None

    selected = max(candidates, key=_period_sort_key)
    if len(candidates) == 1:
        reason = "The document reports a single period."
    else:
        reason = (
            f"Most recent of {len(candidates)} reporting periods found; the "
            "others were recorded but not analysed."
        )
    return PeriodSelection(selected=selected, candidates=candidates, reason=reason)


def _period_sort_key(candidate: PeriodCandidate) -> tuple:
    """Order periods by recency, with a stable fallback.

    A parsed date beats a bare year, and a bare year beats neither. The final
    term keeps the left-most column ahead of an identical one to its right,
    which is the convention a comparative sheet is printed in.
    """
    return (
        candidate.end_date or date.min,
        candidate.year or 0,
        -(candidate.source.column or 0),
    )


def _period_candidates(preliminary: PreliminaryExtraction) -> list[PeriodCandidate]:
    """Find the period column headings.

    A heading row is one whose cells name dates or years rather than figures.
    Each such cell becomes a candidate, keyed to the column it sits in, so a
    figure elsewhere on the page can later be matched to it by position.
    """
    for line in build_lines(preliminary):
        # Every cell is considered, the leading one included: a heading row has
        # no label, so its current-period column *is* cell zero.
        headings = [cell for cell in line.cells if _period_text(cell.text)]
        if not headings:
            continue
        # A row carrying an actual figure is a data row, not a heading row -
        # even if some other cell in it happens to contain a year.
        if any(
            looks_like_amount(cell.text) and not looks_like_year(cell.text)
            for cell in line.cells
        ):
            continue
        return [_candidate_from(line, cell) for cell in headings]

    # No column heading row. The label of a titled sheet often carries the date
    # instead: "Balance Sheet as at 31 March 2024".
    for line in build_lines(preliminary):
        if matches_any(line.label, anchors.TITLE_PHRASES) and _period_text(
            line.label
        ):
            end_date, year = _parse_period(line.label)
            return [
                PeriodCandidate(
                    label=line.label.strip()[:200],
                    end_date=end_date,
                    year=year,
                    source=line.source(),
                )
            ]
    return []


def _candidate_from(line: DocumentLine, cell: Cell) -> PeriodCandidate:
    end_date, year = _parse_period(cell.text)
    return PeriodCandidate(
        label=cell.text.strip()[:200],
        end_date=end_date,
        year=year,
        source=line.source(cell.column),
    )


def _period_text(text: str) -> bool:
    return bool(_DATE_PATTERN.search(text) or _YEAR_PATTERN.search(text))


def _parse_period(text: str) -> tuple[date | None, int | None]:
    """Pull an end date and/or a year out of a heading."""
    match = _DATE_PATTERN.search(text)
    if match:
        day, month_name, year = match.groups()
        month = _MONTHS.get(month_name.lower())
        if month:
            try:
                return date(int(year), month, int(day)), int(year)
            except ValueError:
                logger.info("Ignoring an impossible date in %r", text[:80])

    years = _YEAR_PATTERN.findall(text)
    if years:
        # The later year, so "FY 2023-2024" resolves to 2024.
        return None, max(int(year) for year in years)
    return None, None


# --------------------------------------------------------------------------
# Units and currency - recorded, never applied
# --------------------------------------------------------------------------


def detect_units(preliminary: PreliminaryExtraction) -> UnitHint | None:
    """Record the currency and magnitude the document was printed in.

    **Nothing is scaled.** A sheet marked "in thousands" is stored with its
    figures exactly as printed and the factor noted beside them. Applying the
    factor is a normalisation decision, and normalisation is Module 2's.
    """
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
    return UnitHint(
        currency=currency,
        scale_label=scale_label,
        scale_factor=scale_factor,
        source=source,
    )


# --------------------------------------------------------------------------
# Total lines
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LocatedTotal:
    """One section total, as printed and as parsed, with where it came from."""

    kind: str
    label: str
    raw: str
    value: Decimal
    source: SourceRef


@dataclass
class LocatedTotals:
    """The three totals the accounting-equation check needs."""

    assets: LocatedTotal | None = None
    liabilities: LocatedTotal | None = None
    equity: LocatedTotal | None = None

    @property
    def missing(self) -> list[str]:
        return [
            name
            for name in ("assets", "liabilities", "equity")
            if getattr(self, name) is None
        ]

    @property
    def complete(self) -> bool:
        return not self.missing


def locate_totals(
    preliminary: PreliminaryExtraction,
    *,
    period: PeriodSelection | None = None,
) -> LocatedTotals:
    """Locate the three section totals for the selected reporting period.

    Deliberately narrow: totals only, no line-item vocabulary. On a comparative
    sheet the figure is taken from the selected period's column and no other -
    reading the wrong column would produce a sheet that balances against the
    wrong year.

    Later occurrences win. A Balance Sheet that prints a subtotal and then a
    grand total for the same section puts the grand total last.

    Every label on a row is considered, not only the leading one. A sheet
    printed in the horizontal layout puts Liabilities and Equity in a second
    column of labels, and those totals are as real as the ones on the left -
    see :attr:`DocumentLine.segments`.
    """
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
            if value is None:  # pragma: no cover - figure_for already parsed it
                continue

            setattr(
                totals,
                kind,
                LocatedTotal(
                    kind=kind,
                    label=segment.label.text.strip()[:200],
                    raw=cell.text.strip(),
                    value=value,
                    source=line.source(cell.column),
                ),
            )
    return totals


__all__ = [
    "IDENTIFICATION_THRESHOLD",
    "LocatedTotal",
    "LocatedTotals",
    "detect_units",
    "is_balance_sheet",
    "locate_totals",
    "select_period",
]
