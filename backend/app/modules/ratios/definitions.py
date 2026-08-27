"""The seven ratios, declared once, as data.

Every ratio this system computes is defined here and nowhere else: its formula,
what it means, which canonical categories feed it, and what it does not tell
you. Nothing in this file computes anything - :mod:`app.modules.ratios.service`
does that, reading these declarations.

Keeping the prose beside the specification is the same argument
``extraction/taxonomy.py`` makes for ``Category.description``: a formula
documented in one place and implemented in another will eventually disagree,
and the disagreement will be discovered in a report rather than in a test.
``docs/RATIOS.md`` is generated from this file for exactly that reason.

**Where a ratio has more than one accepted definition, the choice is recorded
in** ``definition`` **and the rejected alternative is named.** Mixing
definitions silently between documents - or between a report and the code that
produced it - would make every comparison meaningless.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.core.schemas import RatioBasis, RatioUnit
from app.modules.extraction.taxonomy import Section, Subsection

# Bumped whenever a formula, an input mapping or a rounding rule changes.
# Stored on every RatioSet, and deliberately separate from TAXONOMY_VERSION: a
# formula change and a vocabulary change are different events, and a stored
# result has to be able to say which of the two moved.
RATIO_SPEC_VERSION = "1.0.0"


class InputKind(str, Enum):
    """Where a quantity's figure comes from.

    The distinction is the whole provenance argument of this module. A section
    total was printed on the document and validated by Module 1; a derived sum
    was assembled here from line items because Module 2 discarded the printed
    subtotals. They are not equally trustworthy and a result says which it used.
    """

    SECTION_TOTAL = "section_total"
    DERIVED_SUM = "derived_sum"
    COMPOSITE = "composite"


_BASIS: dict[InputKind, RatioBasis] = {
    InputKind.SECTION_TOTAL: RatioBasis.SECTION_TOTAL,
    InputKind.DERIVED_SUM: RatioBasis.DERIVED_SUM,
    InputKind.COMPOSITE: RatioBasis.COMPOSITE,
}


@dataclass(frozen=True)
class InputSpec:
    """One quantity a ratio is built from.

    ``include`` restricts a derived sum to named canonical categories, for a
    quantity like cash assets that is a whitelist rather than a whole
    subsection. ``base``/``subtract`` build a composite by taking a quantity and
    removing named categories from it.
    """

    name: str
    kind: InputKind
    section: Section | None = None
    subsection: Subsection | None = None
    include: tuple[str, ...] = ()
    base: InputSpec | None = None
    subtract: tuple[str, ...] = ()

    @property
    def basis(self) -> RatioBasis:
        return _BASIS[self.kind]


# --------------------------------------------------------------------------
# The quantities
# --------------------------------------------------------------------------

# The three grand totals. Module 1 located these by anchor and checked the
# accounting equation against them, so they are what the document said rather
# than what we managed to reassemble.
TOTAL_ASSETS = InputSpec("Total Assets", InputKind.SECTION_TOTAL, section=Section.ASSETS)
TOTAL_LIABILITIES = InputSpec(
    "Total Liabilities", InputKind.SECTION_TOTAL, section=Section.LIABILITIES
)
TOTAL_EQUITY = InputSpec("Total Equity", InputKind.SECTION_TOTAL, section=Section.EQUITY)

# The subsection subtotals. These have to be summed: a Balance Sheet prints
# "Total Current Assets", but Module 2 excludes every total line from
# line_items, so the printed figure is not in the data. Summing the leaves is
# the only route to it - and, because line_items holds no subtotals, a route
# that cannot double-count.
CURRENT_ASSETS = InputSpec(
    "Current Assets",
    InputKind.DERIVED_SUM,
    section=Section.ASSETS,
    subsection=Subsection.CURRENT,
)
CURRENT_LIABILITIES = InputSpec(
    "Current Liabilities",
    InputKind.DERIVED_SUM,
    section=Section.LIABILITIES,
    subsection=Subsection.CURRENT,
)

# Quick assets: current assets less the two categories that cannot reliably be
# turned into cash inside a payment cycle. An absent subtrahend subtracts zero -
# a sheet with no prepaid expenses genuinely has none to remove.
QUICK_ASSETS = InputSpec(
    "Quick Assets",
    InputKind.COMPOSITE,
    base=CURRENT_ASSETS,
    subtract=("inventory", "prepaid_expenses"),
)

# Cash assets: a whitelist, not a subsection. Unlike an absent subtrahend, an
# absent addend is absent rather than zero - reporting a cash ratio of zero for
# a document whose cash line we simply failed to classify would be a fabricated
# finding of insolvency.
CASH_ASSETS = InputSpec(
    "Cash and Equivalents",
    InputKind.DERIVED_SUM,
    section=Section.ASSETS,
    subsection=Subsection.CURRENT,
    include=("cash_and_cash_equivalents", "short_term_investments"),
)


class Operation(str, Enum):
    DIVIDE = "divide"
    SUBTRACT = "subtract"


@dataclass(frozen=True)
class RatioDefinition:
    """One ratio: how to compute it, what it means, and what it hides."""

    name: str
    formula: str
    definition: str
    limitations: str
    unit: RatioUnit
    left: InputSpec
    right: InputSpec
    operation: Operation = Operation.DIVIDE


_SINGLE_PERIOD_CAVEAT = (
    "Computed from a single reporting period, so it carries no trend and no "
    "industry benchmark; a value is only meaningful beside context this system "
    "does not hold."
)


DEFINITIONS: tuple[RatioDefinition, ...] = (
    RatioDefinition(
        name="current_ratio",
        formula="Current Assets / Current Liabilities",
        definition=(
            "Whether the assets expected to become cash within a year cover the "
            "obligations falling due within the same year. A value below 1 means "
            "short-term obligations exceed short-term resources."
        ),
        limitations=(
            "Treats every current asset as equally liquid, which inventory and "
            "prepaid expenses are not - that is what the quick ratio corrects. "
            "Both sides are summed from classified line items rather than read "
            "from a printed subtotal, so an unclassified line understates it. "
            + _SINGLE_PERIOD_CAVEAT
        ),
        unit=RatioUnit.RATIO,
        left=CURRENT_ASSETS,
        right=CURRENT_LIABILITIES,
    ),
    RatioDefinition(
        name="quick_ratio",
        formula="(Current Assets - Inventory - Prepaid Expenses) / Current Liabilities",
        definition=(
            "The acid test: short-term cover counting only assets that can be "
            "realised without first selling stock. This is the SUBTRACTIVE "
            "definition, chosen so that it shares the current ratio's numerator "
            "basis and the two can be read side by side. The additive form - "
            "cash plus short-term investments plus receivables, over current "
            "liabilities - is NOT used here: with a closed six-category "
            "current-asset vocabulary it silently drops anything outside the "
            "whitelist."
        ),
        limitations=(
            "Because it subtracts rather than whitelists, a residual line the "
            "document presents as 'other current assets' is counted as quick, "
            "which flatters liquidity. The inputs list shows exactly what was "
            "included. " + _SINGLE_PERIOD_CAVEAT
        ),
        unit=RatioUnit.RATIO,
        left=QUICK_ASSETS,
        right=CURRENT_LIABILITIES,
    ),
    RatioDefinition(
        name="cash_ratio",
        formula="(Cash and Cash Equivalents + Short-term Investments) / Current Liabilities",
        definition=(
            "The strictest liquidity measure: what could be paid immediately, "
            "without collecting a receivable or selling anything. Marketable "
            "securities are included, the common presentation; a strict "
            "cash-only variant is not used, because it under-reports every sheet "
            "that splits deposits out from cash in hand."
        ),
        limitations=(
            "Deliberately severe - healthy companies routinely run well below 1, "
            "because holding enough cash to retire all current liabilities at "
            "once is poor capital use rather than prudence. Unavailable, not "
            "zero, when neither cash nor short-term investments could be "
            "identified. " + _SINGLE_PERIOD_CAVEAT
        ),
        unit=RatioUnit.RATIO,
        left=CASH_ASSETS,
        right=CURRENT_LIABILITIES,
    ),
    RatioDefinition(
        name="debt_to_equity",
        formula="Total Liabilities / Total Equity",
        definition=(
            "How much of the business is financed by creditors for each unit "
            "financed by shareholders. Uses TOTAL LIABILITIES, not borrowings "
            "alone: the borrowings-only variant needs a debt/non-debt split that "
            "the canonical vocabulary does not draw, and guessing at one would "
            "put an invented boundary inside a headline ratio."
        ),
        limitations=(
            "Uninterpretable on its usual scale when equity is negative - the "
            "result goes negative and a more insolvent company reports a number "
            "closer to zero. The negative_denominator warning marks that case; "
            "the value is never clamped, because hiding insolvency is the worst "
            "thing this system could do. " + _SINGLE_PERIOD_CAVEAT
        ),
        unit=RatioUnit.RATIO,
        left=TOTAL_LIABILITIES,
        right=TOTAL_EQUITY,
    ),
    RatioDefinition(
        name="debt_ratio",
        formula="Total Liabilities / Total Assets",
        definition=(
            "The share of the asset base funded by obligations of any kind. "
            "Uses TOTAL LIABILITIES rather than borrowings alone, for the same "
            "reason as debt-to-equity: the canonical vocabulary draws no "
            "debt/non-debt boundary, and inventing one would put a guess inside "
            "a headline ratio."
        ),
        limitations=(
            "Says nothing about when the debt falls due: a sheet financed "
            "entirely by twenty-year bonds and one financed entirely by "
            "overdrafts report the same figure. Read it beside the current "
            "ratio. " + _SINGLE_PERIOD_CAVEAT
        ),
        unit=RatioUnit.RATIO,
        left=TOTAL_LIABILITIES,
        right=TOTAL_ASSETS,
    ),
    RatioDefinition(
        name="equity_ratio",
        formula="Total Equity / Total Assets",
        definition=(
            "The share of the asset base funded by shareholders. The complement "
            "of the debt ratio on a sheet that balances; both are reported "
            "because both are quoted, and their sum is a useful check."
        ),
        limitations=(
            "Adds no information beyond the debt ratio when the accounting "
            "equation holds. Its value is as a cross-check: if the two do not "
            "sum to 1, the section totals disagree with each other. "
            + _SINGLE_PERIOD_CAVEAT
        ),
        unit=RatioUnit.RATIO,
        left=TOTAL_EQUITY,
        right=TOTAL_ASSETS,
    ),
    RatioDefinition(
        name="working_capital",
        formula="Current Assets - Current Liabilities",
        definition=(
            "The absolute cushion between short-term resources and short-term "
            "obligations. A money amount rather than a ratio, so it shows scale "
            "where the current ratio shows only proportion."
        ),
        limitations=(
            "Being absolute, it cannot be compared between companies of "
            "different sizes - that is the current ratio's job. It carries the "
            "sheet's printed scale, which this system records and never applies: "
            "a sheet printed 'in thousands' yields a figure in thousands. "
            + _SINGLE_PERIOD_CAVEAT
        ),
        unit=RatioUnit.CURRENCY,
        left=CURRENT_ASSETS,
        right=CURRENT_LIABILITIES,
        operation=Operation.SUBTRACT,
    ),
)


_BY_NAME: dict[str, RatioDefinition] = {
    definition.name: definition for definition in DEFINITIONS
}


def names() -> tuple[str, ...]:
    """Every ratio this system computes, in declaration order."""
    return tuple(_BY_NAME)


def get(name: str) -> RatioDefinition | None:
    """The definition named ``name``, or ``None``."""
    return _BY_NAME.get(name)


__all__ = [
    "DEFINITIONS",
    "RATIO_SPEC_VERSION",
    "CASH_ASSETS",
    "CURRENT_ASSETS",
    "CURRENT_LIABILITIES",
    "InputKind",
    "InputSpec",
    "Operation",
    "QUICK_ASSETS",
    "RatioDefinition",
    "TOTAL_ASSETS",
    "TOTAL_EQUITY",
    "TOTAL_LIABILITIES",
    "get",
    "names",
]
