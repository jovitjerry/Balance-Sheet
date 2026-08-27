"""Module 3 - Deterministic Financial Ratio Engine.

Takes the structured, normalized Balance Sheet Module 2 produced and answers
one question: **what do these numbers imply numerically?**

CONSTRAINT: ratios are computed in deterministic Python and are **never**
delegated to an LLM. :func:`compute_ratios` is therefore deliberately
synchronous and pure - no database handle, no LLM client, no I/O of any kind.
Keep it that way: the signature is what makes the constraint structural rather
than merely intended, and it is what makes this module trivially unit-testable.
``tests/test_pipeline.py`` enforces it by reading the imports.

That constraint is not decoration. Module 2's own Q&A benchmark had three of
four candidate models make arithmetic errors on a Balance Sheet containing
fifteen numbers - one of them summing current assets as 550,000 instead of
850,000 and concluding the company could not pay its short-term bills, the
exact opposite of the truth. Every figure below is Python's.

**Nothing here is fabricated.** A ratio whose inputs are absent, or whose
denominator is zero, is reported ``unavailable`` with a machine-readable reason.
A ratio computed from an incomplete set of line items is reported ``partial``,
naming what it left out. Neither is ever a number with the doubt filed off.

Where the figures come from, and why, is :mod:`app.modules.ratios.aggregation`.
What the seven ratios *are* is :mod:`app.modules.ratios.definitions`.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

from app.core.schemas import (
    ExtractedBalanceSheet,
    RatioDiagnostics,
    RatioInput,
    RatioResult,
    RatioSet,
    RatioStatus,
)
from app.modules.extraction import taxonomy
from app.modules.ratios import definitions
from app.modules.ratios.aggregation import (
    REASON_NOT_REPRESENTABLE,
    REASON_ZERO_DENOMINATOR,
    WARNING_NEGATIVE_DENOMINATOR,
    WARNING_NEGATIVE_NUMERATOR,
    WARNING_NEGATIVE_RESULT,
    WARNING_UNMAPPED_INPUTS,
    WARNING_UNPARSED_INPUTS,
    Aggregate,
    SheetIndex,
)
from app.modules.ratios.definitions import Operation, RatioDefinition

# How many decimal places a quotient is reported to. Six is far more than a
# report shows, and enough that 1/3 stays distinguishable from 2/6.
#
# A module constant, NOT a setting. It is part of a documented formula's output
# contract, and a deployment able to change it could change a published result
# without changing a version number.
RATIO_DECIMAL_PLACES = 6

_QUANTUM = Decimal(1).scaleb(-RATIO_DECIMAL_PLACES)

# Decimal128's significand, so a computed quotient cannot exceed what the
# storage boundary in core/money.py will accept.
_PRECISION = 34

# The warnings that mean a value was computed from an incomplete input set.
_COVERAGE_WARNINGS = frozenset({WARNING_UNMAPPED_INPUTS, WARNING_UNPARSED_INPUTS})


def compute_ratios(
    sheet: ExtractedBalanceSheet, *, scale_label: str | None = None
) -> RatioSet:
    """Compute Balance Sheet ratios. Pure, synchronous, deterministic.

    Given the same sheet this returns the same result forever - which is what
    an academic deliverable requires, and what nothing involving a language
    model could promise.

    ``scale_label`` is the magnitude printed on the document ("in thousands"),
    which lives on the *document* rather than on the sheet. It is recorded and
    **never applied**, exactly as Modules 1 and 2 record and never apply it: the
    six quotients are dimensionless so scale cancels out of them, and working
    capital is reported in whatever units the document was printed in.

    The sheet is never mutated.
    """
    index = SheetIndex(sheet)

    return RatioSet(
        ratios=[_compute(definition, index) for definition in definitions.DEFINITIONS],
        spec_version=definitions.RATIO_SPEC_VERSION,
        taxonomy_version=sheet.taxonomy_version,
        currency=sheet.currency,
        scale_label=scale_label,
        diagnostics=RatioDiagnostics(
            duplicate_canonical_labels=index.duplicate_canonical_labels(),
            reconciliation_difference=index.reconciliation_difference(),
            normalization_summary=dict(sheet.normalization_summary or {}),
            unclassified=index.unclassified_inputs(),
        ),
        warnings=_set_warnings(sheet, index),
    )


def _compute(definition: RatioDefinition, index: SheetIndex) -> RatioResult:
    """One ratio, with the evidence for it or the reason there is none."""
    left = index.resolve(definition.left)
    right = index.resolve(definition.right)

    if left.value is None or right.value is None:
        # The reason from whichever side actually failed. Reporting the left
        # one unconditionally would blame current assets for a missing
        # liabilities total.
        return _unavailable(
            definition, left, right, reason=left.reason or right.reason
        )

    if definition.operation is Operation.DIVIDE and right.value == 0:
        # Not infinity, and not an unexplained None. A company with no current
        # liabilities has no current *ratio* - the question the ratio asks does
        # not arise - and saying so is a different statement from saying its
        # liquidity is unbounded.
        return _unavailable(definition, left, right, reason=REASON_ZERO_DENOMINATOR)

    value = _apply(definition.operation, left.value, right.value)
    if value is None:
        return _unavailable(definition, left, right, reason=REASON_NOT_REPRESENTABLE)

    warnings = _warnings(definition, left, right, value)
    covered = _COVERAGE_WARNINGS.isdisjoint(warnings)

    return RatioResult(
        name=definition.name,
        formula=definition.formula,
        definition=definition.definition,
        unit=definition.unit,
        status=RatioStatus.OK if covered else RatioStatus.PARTIAL,
        value=value,
        numerator=left.value,
        denominator=right.value,
        numerator_basis=left.basis,
        denominator_basis=right.basis,
        numerator_inputs=left.inputs,
        denominator_inputs=right.inputs,
        excluded=_merge_excluded(left, right),
        excluded_value=_excluded_value(left, right),
        warnings=warnings,
    )


def _apply(operation: Operation, left: Decimal, right: Decimal) -> Decimal | None:
    """The arithmetic, and the only place rounding happens.

    A subtraction is exact and stays exact: working capital is money, and a
    rounded money figure would not tie back to the sheet it came from.

    A division rounds **once**, at the end. There is no intermediate quantize
    anywhere in this module - the sums feeding it are exact - so "do not
    silently round intermediate calculations" holds by construction rather than
    by discipline.
    """
    if operation is Operation.SUBTRACT:
        return left - right

    try:
        with localcontext() as context:
            context.prec = _PRECISION
            return (left / right).quantize(_QUANTUM, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        # A quotient needing more than 34 significant digits at six decimal
        # places. Unreachable from a real filing; returned as unavailable
        # rather than raised, because this function is total.
        return None


def _warnings(
    definition: RatioDefinition, left: Aggregate, right: Aggregate, value: Decimal
) -> list[str]:
    """Everything a reader should know before believing this number.

    Nothing here changes the value. Signs are preserved exactly as computed:
    negative equity produces a negative debt-to-equity ratio, which is
    mathematically correct and financially meaningless, and clamping it would
    hide insolvency - the single most important thing a Balance Sheet review
    can surface.
    """
    warnings: list[str] = []

    # Coverage first: it is the one that says the figure may be incomplete.
    for warning in (WARNING_UNMAPPED_INPUTS, WARNING_UNPARSED_INPUTS):
        if warning in left.warnings or warning in right.warnings:
            warnings.append(warning)

    if left.value is not None and left.value < 0:
        warnings.append(WARNING_NEGATIVE_NUMERATOR)
    if (
        definition.operation is Operation.DIVIDE
        and right.value is not None
        and right.value < 0
    ):
        warnings.append(WARNING_NEGATIVE_DENOMINATOR)
    if value < 0:
        warnings.append(WARNING_NEGATIVE_RESULT)

    return warnings


def _unavailable(
    definition: RatioDefinition,
    left: Aggregate,
    right: Aggregate,
    *,
    reason: str | None,
) -> RatioResult:
    """A ratio that could not be computed, with everything that was known.

    The inputs that *were* resolved are kept. A reader asking why the current
    ratio is missing is better served by "current assets 850,000, current
    liabilities absent" than by a blank.
    """
    return RatioResult(
        name=definition.name,
        formula=definition.formula,
        definition=definition.definition,
        unit=definition.unit,
        status=RatioStatus.UNAVAILABLE,
        value=None,
        numerator=left.value,
        denominator=right.value,
        numerator_basis=left.basis if left.value is not None else None,
        denominator_basis=right.basis if right.value is not None else None,
        numerator_inputs=left.inputs,
        denominator_inputs=right.inputs,
        excluded=_merge_excluded(left, right),
        excluded_value=_excluded_value(left, right),
        reason=reason,
        warnings=[
            warning
            for warning in (WARNING_UNMAPPED_INPUTS, WARNING_UNPARSED_INPUTS)
            if warning in left.warnings or warning in right.warnings
        ],
    )


def _merge_excluded(left: Aggregate, right: Aggregate) -> list[RatioInput]:
    """Excluded inputs from both sides, without repeating a shared one.

    The three liquidity ratios share a denominator, and a composite shares its
    base's exclusions, so the same line arrives twice and would otherwise be
    counted twice in ``excluded_value`` - inflating exactly the figure a reader
    uses to bound how wrong the ratio might be.
    """
    merged: list[RatioInput] = []
    seen: set[tuple[str, str]] = set()
    for item in [*left.excluded, *right.excluded]:
        key = (item.label, str(item.value))
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _excluded_value(left: Aggregate, right: Aggregate) -> Decimal | None:
    excluded = _merge_excluded(left, right)
    if not excluded:
        return None
    return sum((item.value for item in excluded), Decimal(0))


def _set_warnings(sheet: ExtractedBalanceSheet, index: SheetIndex) -> list[str]:
    """Warnings about the sheet as a whole rather than about one ratio."""
    warnings: list[str] = []
    if sheet.taxonomy_version and sheet.taxonomy_version != taxonomy.TAXONOMY_VERSION:
        warnings.append(
            f"normalized under taxonomy {sheet.taxonomy_version}; this engine "
            f"reads {taxonomy.TAXONOMY_VERSION}"
        )
    if index.unclassified:
        warnings.append(
            f"{len(index.unclassified)} line item(s) could not be classified and "
            "contributed to no derived subtotal"
        )
    return warnings


__all__ = ["RATIO_DECIMAL_PLACES", "compute_ratios"]
