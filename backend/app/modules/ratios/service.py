from __future__ import annotations
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext
from app.core.schemas import ExtractedBalanceSheet, RatioDiagnostics, RatioInput, RatioResult, RatioSet, RatioStatus
from app.modules.extraction import taxonomy
from app.modules.ratios import definitions
from app.modules.ratios.aggregation import REASON_NOT_REPRESENTABLE, REASON_ZERO_DENOMINATOR, WARNING_NEGATIVE_DENOMINATOR, WARNING_NEGATIVE_NUMERATOR, WARNING_NEGATIVE_RESULT, WARNING_UNMAPPED_INPUTS, WARNING_UNPARSED_INPUTS, Aggregate, SheetIndex
from app.modules.ratios.definitions import Operation, RatioDefinition
RATIO_DECIMAL_PLACES = 6
_QUANTUM = Decimal(1).scaleb(-RATIO_DECIMAL_PLACES)
_PRECISION = 34
_COVERAGE_WARNINGS = frozenset({WARNING_UNMAPPED_INPUTS, WARNING_UNPARSED_INPUTS})

def compute_ratios(sheet: ExtractedBalanceSheet, *, scale_label: str | None=None) -> RatioSet:
    index = SheetIndex(sheet)
    return RatioSet(ratios=[_compute(definition, index) for definition in definitions.DEFINITIONS], spec_version=definitions.RATIO_SPEC_VERSION, taxonomy_version=sheet.taxonomy_version, currency=sheet.currency, scale_label=scale_label, diagnostics=RatioDiagnostics(duplicate_canonical_labels=index.duplicate_canonical_labels(), reconciliation_difference=index.reconciliation_difference(), normalization_summary=dict(sheet.normalization_summary or {}), unclassified=index.unclassified_inputs()), warnings=_set_warnings(sheet, index))

def _compute(definition: RatioDefinition, index: SheetIndex) -> RatioResult:
    left = index.resolve(definition.left)
    right = index.resolve(definition.right)
    if left.value is None or right.value is None:
        return _unavailable(definition, left, right, reason=left.reason or right.reason)
    if definition.operation is Operation.DIVIDE and right.value == 0:
        return _unavailable(definition, left, right, reason=REASON_ZERO_DENOMINATOR)
    value = _apply(definition.operation, left.value, right.value)
    if value is None:
        return _unavailable(definition, left, right, reason=REASON_NOT_REPRESENTABLE)
    warnings = _warnings(definition, left, right, value)
    covered = _COVERAGE_WARNINGS.isdisjoint(warnings)
    return RatioResult(name=definition.name, formula=definition.formula, definition=definition.definition, unit=definition.unit, status=RatioStatus.OK if covered else RatioStatus.PARTIAL, value=value, numerator=left.value, denominator=right.value, numerator_basis=left.basis, denominator_basis=right.basis, numerator_inputs=left.inputs, denominator_inputs=right.inputs, excluded=_merge_excluded(left, right), excluded_value=_excluded_value(left, right), warnings=warnings)

def _apply(operation: Operation, left: Decimal, right: Decimal) -> Decimal | None:
    if operation is Operation.SUBTRACT:
        return left - right
    try:
        with localcontext() as context:
            context.prec = _PRECISION
            return (left / right).quantize(_QUANTUM, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None

def _warnings(definition: RatioDefinition, left: Aggregate, right: Aggregate, value: Decimal) -> list[str]:
    warnings: list[str] = []
    for warning in (WARNING_UNMAPPED_INPUTS, WARNING_UNPARSED_INPUTS):
        if warning in left.warnings or warning in right.warnings:
            warnings.append(warning)
    if left.value is not None and left.value < 0:
        warnings.append(WARNING_NEGATIVE_NUMERATOR)
    if definition.operation is Operation.DIVIDE and right.value is not None and (right.value < 0):
        warnings.append(WARNING_NEGATIVE_DENOMINATOR)
    if value < 0:
        warnings.append(WARNING_NEGATIVE_RESULT)
    return warnings

def _unavailable(definition: RatioDefinition, left: Aggregate, right: Aggregate, *, reason: str | None) -> RatioResult:
    return RatioResult(name=definition.name, formula=definition.formula, definition=definition.definition, unit=definition.unit, status=RatioStatus.UNAVAILABLE, value=None, numerator=left.value, denominator=right.value, numerator_basis=left.basis if left.value is not None else None, denominator_basis=right.basis if right.value is not None else None, numerator_inputs=left.inputs, denominator_inputs=right.inputs, excluded=_merge_excluded(left, right), excluded_value=_excluded_value(left, right), reason=reason, warnings=[warning for warning in (WARNING_UNMAPPED_INPUTS, WARNING_UNPARSED_INPUTS) if warning in left.warnings or warning in right.warnings])

def _merge_excluded(left: Aggregate, right: Aggregate) -> list[RatioInput]:
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
    warnings: list[str] = []
    if sheet.taxonomy_version and sheet.taxonomy_version != taxonomy.TAXONOMY_VERSION:
        warnings.append(f'normalized under taxonomy {sheet.taxonomy_version}; this engine reads {taxonomy.TAXONOMY_VERSION}')
    if index.unclassified:
        warnings.append(f'{len(index.unclassified)} line item(s) could not be classified and contributed to no derived subtotal')
    return warnings
__all__ = ['RATIO_DECIMAL_PLACES', 'compute_ratios']
