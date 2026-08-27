"""Turning a Balance Sheet into the quantities a ratio is built from.

This is where the provenance rules live, and it is the part of Module 3 that
can actually be wrong. The arithmetic afterwards is a division.

**One rule governs everything here:**

    Prefer what the document printed and Module 1 validated.
    Derive only what was not printed.

So the three grand totals come from :class:`BalanceSheetSection.total` - located
by anchor and checked against the accounting equation in Module 1 - while
current and non-current subtotals have to be summed from line items, because
Module 2 excludes every printed subtotal from ``line_items`` and the figure
therefore does not exist in the data.

That exclusion is also what makes summing safe. ``line_items`` holds leaves and
only leaves, and the grand totals live in a different field entirely, so there
is nothing summable here that contains anything else summable. The
``350,000 + 280,000 + 125,000 + 850,000`` failure cannot be constructed from
this data model - and :func:`_guard` asserts it anyway, because a Module 2
regression would otherwise inflate a section in silence.

**Classification comes from the canonical category, never from the printed
heading.** ``taxonomy.get(canonical_label)`` decides whether a line is a current
asset. ``LineItem.subsection`` is the heading the line sat under, and a great
many Balance Sheets print no current/non-current headings at all - on those,
heading-based classification would compute nothing. The one thing the printed
heading is allowed to do is *narrow* the set of quantities an **unclassified**
line could have belonged to (see :func:`_could_belong_to`); it never places a
line into a sum.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from app.core.schemas import (
    BalanceSheetSection,
    ExtractedBalanceSheet,
    ExtractionStatus,
    LineItem,
    NormalizationStatus,
    RatioBasis,
    RatioInput,
)
from app.modules.extraction import taxonomy
from app.modules.extraction.extraction import is_total_line
from app.modules.extraction.taxonomy import Section, Subsection
from app.modules.ratios.definitions import InputKind, InputSpec

# ---- The closed reason vocabulary -----------------------------------------
# Every non-`ok` outcome names one of these. Kept together so the set really is
# closed and a test can enumerate it; a free-text reason would be unusable to
# Module 4 and to the frontend.

REASON_MISSING_SECTION_TOTAL = "missing_section_total"
REASON_NO_CLASSIFIED_INPUTS = "no_classified_inputs"
REASON_ZERO_DENOMINATOR = "zero_denominator"
REASON_NOT_EXTRACTED = "not_extracted"
# A quotient too large to hold in Decimal128 at the stored precision. Not
# reachable from a real Balance Sheet, but reported rather than raised: this
# module is total, and a figure nobody can store is not a figure to return.
REASON_NOT_REPRESENTABLE = "not_representable"

WARNING_UNMAPPED_INPUTS = "unmapped_inputs"
WARNING_UNPARSED_INPUTS = "unparsed_inputs"
WARNING_NEGATIVE_NUMERATOR = "negative_numerator"
WARNING_NEGATIVE_DENOMINATOR = "negative_denominator"
WARNING_NEGATIVE_RESULT = "negative_result"

REASONS: frozenset[str] = frozenset(
    {
        REASON_MISSING_SECTION_TOTAL,
        REASON_NO_CLASSIFIED_INPUTS,
        REASON_ZERO_DENOMINATOR,
        REASON_NOT_EXTRACTED,
        REASON_NOT_REPRESENTABLE,
    }
)

WARNINGS: frozenset[str] = frozenset(
    {
        WARNING_UNMAPPED_INPUTS,
        WARNING_UNPARSED_INPUTS,
        WARNING_NEGATIVE_NUMERATOR,
        WARNING_NEGATIVE_DENOMINATOR,
        WARNING_NEGATIVE_RESULT,
    }
)

_SECTION_FIELDS: dict[Section, str] = {
    Section.ASSETS: "assets",
    Section.LIABILITIES: "liabilities",
    Section.EQUITY: "equity",
}


@dataclass(frozen=True)
class Aggregate:
    """A resolved quantity, and the evidence behind it.

    ``value`` is ``None`` only when ``reason`` says why. ``excluded`` holds the
    lines that carried a figure and would have been eligible, had anyone been
    able to say what they were.
    """

    spec: InputSpec
    value: Decimal | None
    basis: RatioBasis
    inputs: list[RatioInput] = field(default_factory=list)
    excluded: list[RatioInput] = field(default_factory=list)
    excluded_value: Decimal | None = None
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return self.value is not None


@dataclass(frozen=True)
class _Classified:
    """A line item whose canonical category is known."""

    item: LineItem
    label: str  # canonical
    section: Section
    subsection: Subsection | None
    value: Decimal


@dataclass(frozen=True)
class _Unclassified:
    """A line item that cannot be summed, and everything known about where it sits.

    Two different things land here: a line nobody could map, and a line that
    mapped perfectly well but whose printed figure would not parse. The second
    still has a category, which is worth keeping - it says precisely which
    quantities the missing figure would have affected, instead of forcing every
    one of them to report itself incomplete.

    ``printed_subsection`` is the heading the line sat under, when the document
    had one. Both fields are used only to narrow which derived quantities this
    line could have belonged to - never to give it a category it does not have.
    """

    item: LineItem
    section: Section
    printed_subsection: Subsection | None
    value: Decimal | None
    category: taxonomy.Category | None = None


class SheetIndex:
    """Every line item of a sheet, sorted into what can and cannot be used.

    Built once per sheet and read by every ratio, so the classification pass
    runs a single time and every ratio sees exactly the same view of the
    document.
    """

    def __init__(self, sheet: ExtractedBalanceSheet) -> None:
        self.sheet = sheet
        self.classified: list[_Classified] = []
        self.unclassified: list[_Unclassified] = []
        self.totals: dict[Section, Decimal | None] = {}
        self.has_line_items = False

        for section, field_name in _SECTION_FIELDS.items():
            part: BalanceSheetSection = getattr(sheet, field_name)
            self.totals[section] = part.total
            for item in part.line_items:
                self.has_line_items = True
                self._sort(item, section)

    def _sort(self, item: LineItem, section: Section) -> None:
        _guard(item)
        printed = _printed_subsection(item)
        category = _category_of(item)

        if category is None or item.value is None:
            # Either nobody could say what the line is, or its figure would not
            # parse. Both are excluded from every sum, and both are reported.
            self.unclassified.append(
                _Unclassified(
                    item=item,
                    section=section,
                    printed_subsection=printed,
                    value=item.value,
                    category=category,
                )
            )
            return

        # The section a normalized item belongs to is the canonical category's,
        # which taxonomy.fits() already proved consistent with the printed one
        # back in Module 2 - so this cannot contradict `section`.
        self.classified.append(
            _Classified(
                item=item,
                label=category.label,
                section=category.section,
                subsection=category.subsection,
                value=item.value,
            )
        )

    # -- resolution ---------------------------------------------------------

    def resolve(self, spec: InputSpec) -> Aggregate:
        """The quantity ``spec`` describes, as read from this sheet."""
        if spec.kind is InputKind.SECTION_TOTAL:
            return self._section_total(spec)
        if spec.kind is InputKind.COMPOSITE:
            return self._composite(spec)
        return self._derived_sum(spec)

    def _section_total(self, spec: InputSpec) -> Aggregate:
        """Module 1's printed total. Independent of extraction completeness.

        This is why the leverage ratios survive a document nobody could
        normalize: the figure was read off the page and validated long before
        any label was interpreted.
        """
        assert spec.section is not None
        total = self.totals.get(spec.section)
        if total is None:
            return Aggregate(
                spec=spec,
                value=None,
                basis=spec.basis,
                reason=REASON_MISSING_SECTION_TOTAL,
            )

        part: BalanceSheetSection = getattr(self.sheet, _SECTION_FIELDS[spec.section])
        return Aggregate(
            spec=spec,
            value=total,
            basis=spec.basis,
            inputs=[
                RatioInput(
                    canonical_label=None,
                    label=part.total_label or spec.name,
                    value=total,
                    source=part.total_source,
                )
            ],
        )

    def _derived_sum(self, spec: InputSpec) -> Aggregate:
        """Summed from classified leaves, because the printed subtotal is gone."""
        members = [entry for entry in self.classified if _matches(entry, spec)]
        coverage = _coverage(self, spec)

        if not members:
            # "Module 2 never ran" and "Module 2 ran and mapped nothing usable"
            # are different failures and a reader needs to tell them apart: the
            # first is a pipeline gap, the second is a document problem.
            return Aggregate(
                spec=spec,
                value=None,
                basis=spec.basis,
                reason=(
                    REASON_NO_CLASSIFIED_INPUTS
                    if self.has_line_items
                    else REASON_NOT_EXTRACTED
                ),
                excluded=coverage.excluded,
                excluded_value=coverage.excluded_value,
                warnings=coverage.warnings,
            )

        return Aggregate(
            spec=spec,
            value=sum((entry.value for entry in members), Decimal(0)),
            basis=spec.basis,
            inputs=[_as_input(entry) for entry in members],
            excluded=coverage.excluded,
            excluded_value=coverage.excluded_value,
            warnings=coverage.warnings,
        )

    def _composite(self, spec: InputSpec) -> Aggregate:
        """A base quantity with named categories removed.

        Built by *filtering the base's own inputs* rather than by subtracting a
        second sum. The two are arithmetically identical, and filtering leaves
        the result's input list showing precisely what was counted - so "why is
        quick 500,000?" is answered by reading it, not by re-deriving it.
        """
        assert spec.base is not None
        base = self.resolve(spec.base)
        if not base.available:
            return Aggregate(
                spec=spec,
                value=None,
                basis=spec.basis,
                reason=base.reason,
                excluded=base.excluded,
                excluded_value=base.excluded_value,
                warnings=list(base.warnings),
            )

        removed = set(spec.subtract)
        kept = [item for item in base.inputs if item.canonical_label not in removed]
        return Aggregate(
            spec=spec,
            value=sum((item.value for item in kept), Decimal(0)),
            basis=spec.basis,
            inputs=kept,
            excluded=base.excluded,
            excluded_value=base.excluded_value,
            warnings=list(base.warnings),
        )

    # -- diagnostics --------------------------------------------------------

    def duplicate_canonical_labels(self) -> dict[str, int]:
        """Canonical labels claimed by more than one line.

        Not a double count and never de-duplicated: two printed lines are two
        figures with two source references, and summing them is right. Reported
        so a reviewer can spot a document that printed the same line twice.
        """
        counts = Counter(entry.label for entry in self.classified)
        return {label: count for label, count in sorted(counts.items()) if count > 1}

    def unclassified_inputs(self) -> list[RatioInput]:
        """Every line carrying a figure that no ratio could use."""
        return [
            RatioInput(
                canonical_label=None,
                label=entry.item.label,
                value=entry.value,
                source=entry.item.source,
            )
            for entry in self.unclassified
            if entry.value is not None
        ]

    def reconciliation_difference(self) -> dict[str, Decimal]:
        """Per section, how far Module 2's line items fell short of the total."""
        differences: dict[str, Decimal] = {}
        for section, field_name in _SECTION_FIELDS.items():
            part: BalanceSheetSection = getattr(self.sheet, field_name)
            if part.reconciliation_difference is not None:
                differences[section.value] = part.reconciliation_difference
        return differences


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _guard(item: LineItem) -> None:
    """Refuse to aggregate anything that announces itself as a total.

    Module 2 already excluded these, so this never fires on correct data. It
    exists because the failure it catches is invisible: a subtotal summed
    alongside the items it summarises produces a section total roughly twice
    its true size, which is a plausible-looking number on a document nobody
    checks by hand.

    Uses Module 2's own predicate rather than a second copy of the rule - two
    copies could disagree, and only one of them would be the one that ran.
    """
    if is_total_line(item.label):
        raise AssertionError(
            f"{item.label!r} is a total line and must not reach aggregation - "
            "Module 2's line-item extraction should have excluded it"
        )


def _category_of(item: LineItem) -> taxonomy.Category | None:
    """The canonical category of a line item, or ``None`` if it has none.

    A canonical label exists if and only if normalization succeeded, so this is
    a status check rather than a heuristic. A label that is not in *this*
    taxonomy version is treated as unclassified too: a mapping stored under an
    older vocabulary is not a mapping this ratio set can honour.
    """
    normalization = item.normalization
    if normalization is None:
        return None
    if normalization.status is not NormalizationStatus.NORMALIZED:
        return None
    if normalization.canonical_label is None:
        return None
    return taxonomy.get(normalization.canonical_label)


def _printed_subsection(item: LineItem) -> Subsection | None:
    """The heading the line was printed under, if the document had one."""
    if item.subsection is None:
        return None
    try:
        return Subsection(item.subsection)
    except ValueError:
        return None


def _matches(entry: _Classified, spec: InputSpec) -> bool:
    """Whether a classified line belongs to the quantity ``spec`` describes."""
    if spec.section is not None and entry.section is not spec.section:
        return False
    if spec.subsection is not None and entry.subsection is not spec.subsection:
        return False
    if spec.include and entry.label not in spec.include:
        return False
    return True


def _could_belong_to(entry: _Unclassified, spec: InputSpec) -> bool:
    """Whether an unusable line might have contributed to this quantity.

    Deliberately generous: a line with no category could be almost anything, so
    whatever is not ruled out has to count as possible. Two things can rule
    something out, and both only ever *shrink* the excluded set - neither ever
    adds a figure to a sum.

    A **known category**, which a line has when its label normalized but its
    figure would not parse. That says exactly where the missing number belonged.

    The **printed heading**, otherwise: a line printed under "Non-Current
    Assets" cannot be a current asset whatever its label says.
    """
    if entry.category is not None:
        # The figure is missing, but what it was is not in doubt.
        if spec.section is not None and entry.category.section is not spec.section:
            return False
        if spec.subsection is not None and entry.category.subsection is not spec.subsection:
            return False
        return not spec.include or entry.category.label in spec.include

    if spec.section is not None and entry.section is not spec.section:
        return False
    if (
        spec.subsection is not None
        and entry.printed_subsection is not None
        and entry.printed_subsection is not spec.subsection
    ):
        return False
    return True


@dataclass(frozen=True)
class _Coverage:
    """How complete a derived sum was able to be."""

    excluded: list[RatioInput] = field(default_factory=list)
    excluded_value: Decimal | None = None
    warnings: list[str] = field(default_factory=list)


def _coverage(index: SheetIndex, spec: InputSpec) -> _Coverage:
    """What this quantity had to leave out, and why that matters.

    A derived sum is only as complete as the normalization behind it. Every
    line that carried a figure and could have belonged here, but had no
    category, is named - so a reader can bound the true value rather than
    guess at it.
    """
    candidates = [entry for entry in index.unclassified if _could_belong_to(entry, spec)]
    if not candidates:
        return _Coverage()

    excluded = [
        RatioInput(
            canonical_label=None,
            label=entry.item.label,
            value=entry.value,
            source=entry.item.source,
        )
        for entry in candidates
        if entry.value is not None
    ]
    warnings: list[str] = []
    if excluded:
        warnings.append(WARNING_UNMAPPED_INPUTS)
    if any(entry.item.status is ExtractionStatus.UNPARSED_VALUE for entry in candidates):
        warnings.append(WARNING_UNPARSED_INPUTS)

    total = sum((item.value for item in excluded), Decimal(0)) if excluded else None
    return _Coverage(excluded=excluded, excluded_value=total, warnings=warnings)


def _as_input(entry: _Classified) -> RatioInput:
    return RatioInput(
        canonical_label=entry.label,
        label=entry.item.label,
        value=entry.value,
        source=entry.item.source,
    )


__all__ = [
    "REASONS",
    "REASON_MISSING_SECTION_TOTAL",
    "REASON_NOT_EXTRACTED",
    "REASON_NOT_REPRESENTABLE",
    "REASON_NO_CLASSIFIED_INPUTS",
    "REASON_ZERO_DENOMINATOR",
    "WARNINGS",
    "WARNING_NEGATIVE_DENOMINATOR",
    "WARNING_NEGATIVE_NUMERATOR",
    "WARNING_NEGATIVE_RESULT",
    "WARNING_UNMAPPED_INPUTS",
    "WARNING_UNPARSED_INPUTS",
    "Aggregate",
    "SheetIndex",
]
