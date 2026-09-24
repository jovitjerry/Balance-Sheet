from __future__ import annotations
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from app.core.schemas import BalanceSheetSection, ExtractedBalanceSheet, ExtractionStatus, LineItem, NormalizationStatus, RatioBasis, RatioInput
from app.modules.extraction import taxonomy
from app.modules.extraction.extraction import is_total_line
from app.modules.extraction.taxonomy import Section, Subsection
from app.modules.ratios.definitions import InputKind, InputSpec
REASON_MISSING_SECTION_TOTAL = 'missing_section_total'
REASON_NO_CLASSIFIED_INPUTS = 'no_classified_inputs'
REASON_ZERO_DENOMINATOR = 'zero_denominator'
REASON_NOT_EXTRACTED = 'not_extracted'
REASON_NOT_REPRESENTABLE = 'not_representable'
WARNING_UNMAPPED_INPUTS = 'unmapped_inputs'
WARNING_UNPARSED_INPUTS = 'unparsed_inputs'
WARNING_NEGATIVE_NUMERATOR = 'negative_numerator'
WARNING_NEGATIVE_DENOMINATOR = 'negative_denominator'
WARNING_NEGATIVE_RESULT = 'negative_result'
REASONS: frozenset[str] = frozenset({REASON_MISSING_SECTION_TOTAL, REASON_NO_CLASSIFIED_INPUTS, REASON_ZERO_DENOMINATOR, REASON_NOT_EXTRACTED, REASON_NOT_REPRESENTABLE})
WARNINGS: frozenset[str] = frozenset({WARNING_UNMAPPED_INPUTS, WARNING_UNPARSED_INPUTS, WARNING_NEGATIVE_NUMERATOR, WARNING_NEGATIVE_DENOMINATOR, WARNING_NEGATIVE_RESULT})
_SECTION_FIELDS: dict[Section, str] = {Section.ASSETS: 'assets', Section.LIABILITIES: 'liabilities', Section.EQUITY: 'equity'}

@dataclass(frozen=True)
class Aggregate:
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
    item: LineItem
    label: str
    section: Section
    subsection: Subsection | None
    value: Decimal

@dataclass(frozen=True)
class _Unclassified:
    item: LineItem
    section: Section
    printed_subsection: Subsection | None
    value: Decimal | None
    category: taxonomy.Category | None = None

class SheetIndex:

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
            self.unclassified.append(_Unclassified(item=item, section=section, printed_subsection=printed, value=item.value, category=category))
            return
        self.classified.append(_Classified(item=item, label=category.label, section=category.section, subsection=category.subsection, value=item.value))

    def resolve(self, spec: InputSpec) -> Aggregate:
        if spec.kind is InputKind.SECTION_TOTAL:
            return self._section_total(spec)
        if spec.kind is InputKind.COMPOSITE:
            return self._composite(spec)
        return self._derived_sum(spec)

    def _section_total(self, spec: InputSpec) -> Aggregate:
        assert spec.section is not None
        total = self.totals.get(spec.section)
        if total is None:
            return Aggregate(spec=spec, value=None, basis=spec.basis, reason=REASON_MISSING_SECTION_TOTAL)
        part: BalanceSheetSection = getattr(self.sheet, _SECTION_FIELDS[spec.section])
        return Aggregate(spec=spec, value=total, basis=spec.basis, inputs=[RatioInput(canonical_label=None, label=part.total_label or spec.name, value=total, source=part.total_source)])

    def _derived_sum(self, spec: InputSpec) -> Aggregate:
        members = [entry for entry in self.classified if _matches(entry, spec)]
        coverage = _coverage(self, spec)
        if not members:
            return Aggregate(spec=spec, value=None, basis=spec.basis, reason=REASON_NO_CLASSIFIED_INPUTS if self.has_line_items else REASON_NOT_EXTRACTED, excluded=coverage.excluded, excluded_value=coverage.excluded_value, warnings=coverage.warnings)
        return Aggregate(spec=spec, value=sum((entry.value for entry in members), Decimal(0)), basis=spec.basis, inputs=[_as_input(entry) for entry in members], excluded=coverage.excluded, excluded_value=coverage.excluded_value, warnings=coverage.warnings)

    def _composite(self, spec: InputSpec) -> Aggregate:
        assert spec.base is not None
        base = self.resolve(spec.base)
        if not base.available:
            return Aggregate(spec=spec, value=None, basis=spec.basis, reason=base.reason, excluded=base.excluded, excluded_value=base.excluded_value, warnings=list(base.warnings))
        removed = set(spec.subtract)
        kept = [item for item in base.inputs if item.canonical_label not in removed]
        return Aggregate(spec=spec, value=sum((item.value for item in kept), Decimal(0)), basis=spec.basis, inputs=kept, excluded=base.excluded, excluded_value=base.excluded_value, warnings=list(base.warnings))

    def duplicate_canonical_labels(self) -> dict[str, int]:
        counts = Counter((entry.label for entry in self.classified))
        return {label: count for label, count in sorted(counts.items()) if count > 1}

    def unclassified_inputs(self) -> list[RatioInput]:
        return [RatioInput(canonical_label=None, label=entry.item.label, value=entry.value, source=entry.item.source) for entry in self.unclassified if entry.value is not None]

    def reconciliation_difference(self) -> dict[str, Decimal]:
        differences: dict[str, Decimal] = {}
        for section, field_name in _SECTION_FIELDS.items():
            part: BalanceSheetSection = getattr(self.sheet, field_name)
            if part.reconciliation_difference is not None:
                differences[section.value] = part.reconciliation_difference
        return differences

def _guard(item: LineItem) -> None:
    if is_total_line(item.label):
        raise AssertionError(f"{item.label!r} is a total line and must not reach aggregation - Module 2's line-item extraction should have excluded it")

def _category_of(item: LineItem) -> taxonomy.Category | None:
    normalization = item.normalization
    if normalization is None:
        return None
    if normalization.status is not NormalizationStatus.NORMALIZED:
        return None
    if normalization.canonical_label is None:
        return None
    return taxonomy.get(normalization.canonical_label)

def _printed_subsection(item: LineItem) -> Subsection | None:
    if item.subsection is None:
        return None
    try:
        return Subsection(item.subsection)
    except ValueError:
        return None

def _matches(entry: _Classified, spec: InputSpec) -> bool:
    if spec.section is not None and entry.section is not spec.section:
        return False
    if spec.subsection is not None and entry.subsection is not spec.subsection:
        return False
    if spec.include and entry.label not in spec.include:
        return False
    return True

def _could_belong_to(entry: _Unclassified, spec: InputSpec) -> bool:
    if entry.category is not None:
        if spec.section is not None and entry.category.section is not spec.section:
            return False
        if spec.subsection is not None and entry.category.subsection is not spec.subsection:
            return False
        return not spec.include or entry.category.label in spec.include
    if spec.section is not None and entry.section is not spec.section:
        return False
    if spec.subsection is not None and entry.printed_subsection is not None and (entry.printed_subsection is not spec.subsection):
        return False
    return True

@dataclass(frozen=True)
class _Coverage:
    excluded: list[RatioInput] = field(default_factory=list)
    excluded_value: Decimal | None = None
    warnings: list[str] = field(default_factory=list)

def _coverage(index: SheetIndex, spec: InputSpec) -> _Coverage:
    candidates = [entry for entry in index.unclassified if _could_belong_to(entry, spec)]
    if not candidates:
        return _Coverage()
    excluded = [RatioInput(canonical_label=None, label=entry.item.label, value=entry.value, source=entry.item.source) for entry in candidates if entry.value is not None]
    warnings: list[str] = []
    if excluded:
        warnings.append(WARNING_UNMAPPED_INPUTS)
    if any((entry.item.status is ExtractionStatus.UNPARSED_VALUE for entry in candidates)):
        warnings.append(WARNING_UNPARSED_INPUTS)
    total = sum((item.value for item in excluded), Decimal(0)) if excluded else None
    return _Coverage(excluded=excluded, excluded_value=total, warnings=warnings)

def _as_input(entry: _Classified) -> RatioInput:
    return RatioInput(canonical_label=entry.label, label=entry.item.label, value=entry.value, source=entry.item.source)
__all__ = ['REASONS', 'REASON_MISSING_SECTION_TOTAL', 'REASON_NOT_EXTRACTED', 'REASON_NOT_REPRESENTABLE', 'REASON_NO_CLASSIFIED_INPUTS', 'REASON_ZERO_DENOMINATOR', 'WARNINGS', 'WARNING_NEGATIVE_DENOMINATOR', 'WARNING_NEGATIVE_NUMERATOR', 'WARNING_NEGATIVE_RESULT', 'WARNING_UNMAPPED_INPUTS', 'WARNING_UNPARSED_INPUTS', 'Aggregate', 'SheetIndex']
