from __future__ import annotations
from decimal import Decimal
from app.core.schemas import BalanceSheetDocument, BalanceSheetSection, Evidence, EvidenceKind, RatioResult, RatioStatus
from app.modules.insights.routing import RouteDecision
from app.modules.ratios import definitions
MAX_LINE_ITEM_FACTS = 40
_SECTION_LABELS: dict[str, str] = {'assets': 'Total assets', 'liabilities': 'Total liabilities', 'equity': 'Total equity'}

def facts_for(document: BalanceSheetDocument, *, decision: RouteDecision) -> list[Evidence]:
    facts: list[Evidence] = []
    if document.equation_check is not None:
        check = document.equation_check
        facts.append(Evidence(id='F0', kind=EvidenceKind.EQUATION, label='Accounting equation', value=str(check.total_assets), detail=f"Total assets {check.total_assets} = total liabilities {check.total_liabilities} + total equity {check.total_equity}; {('balances' if check.balanced else 'does NOT balance')}"))
    extracted = document.extracted
    if extracted is None:
        return facts
    index = 1
    for field_name, label in _SECTION_LABELS.items():
        part: BalanceSheetSection = getattr(extracted, field_name)
        facts.append(Evidence(id=f'F{index}', kind=EvidenceKind.SECTION_TOTAL, label=label, value=str(part.total), detail=part.total_label, source=part.total_source))
        index += 1
    for item in _ordered_line_items(extracted, decision)[:MAX_LINE_ITEM_FACTS]:
        facts.append(Evidence(id=f'F{index}', kind=EvidenceKind.LINE_ITEM, label=item.label, value=str(item.value) if item.value is not None else None, detail=_line_detail(item), source=item.source))
        index += 1
    facts.extend(_ratio_facts(document, decision))
    facts.extend(_coverage_facts(document))
    return facts

def _ordered_line_items(extracted, decision: RouteDecision):
    named_labels = set(decision.matched_labels)
    named_concepts = set(decision.matched_concepts)
    items = [item for field_name in ('assets', 'liabilities', 'equity') for item in getattr(extracted, field_name).line_items]

    def relevance(item) -> int:
        if item.label in named_labels:
            return 0
        canonical = _canonical_of(item)
        return 1 if canonical and canonical in named_concepts else 2
    return sorted(items, key=relevance)

def _canonical_of(item) -> str | None:
    normalization = item.normalization
    return normalization.canonical_label if normalization else None

def _line_detail(item) -> str | None:
    parts: list[str] = []
    canonical = _canonical_of(item)
    if canonical:
        parts.append(canonical)
    elif item.normalization is not None:
        parts.append(f'not classified ({item.normalization.status.value})')
    if item.subsection:
        parts.append(item.subsection)
    return ', '.join(parts) if parts else None

def _ratio_facts(document: BalanceSheetDocument, decision: RouteDecision) -> list[Evidence]:
    if document.ratios is None:
        return []
    named = set(decision.matched_concepts)
    ordered = sorted(document.ratios.ratios, key=lambda result: 0 if result.name in named else 1)
    return [Evidence(id=f'R{position}', kind=EvidenceKind.RATIO, label=result.name, value=str(result.value) if result.value is not None else None, detail=_ratio_detail(result)) for position, result in enumerate(ordered, start=1)]

def _ratio_detail(result: RatioResult) -> str:
    parts = [result.formula]
    if result.status is RatioStatus.UNAVAILABLE:
        parts.append(f'UNAVAILABLE ({result.reason})')
    else:
        if result.numerator is not None and result.denominator is not None:
            parts.append(f'numerator {result.numerator}, denominator {result.denominator}')
        if result.status is not RatioStatus.OK:
            parts.append(f'status {result.status.value}')
        if result.warnings:
            parts.append('warnings: ' + ', '.join(result.warnings))
    definition = definitions.get(result.name)
    if definition is not None:
        parts.append('limitation: ' + _first_sentence(definition.limitations))
    return '; '.join(parts)

def _first_sentence(text: str) -> str:
    sentence, _, _ = text.partition('. ')
    return sentence.strip().rstrip('.') + '.'

def _coverage_facts(document: BalanceSheetDocument) -> list[Evidence]:
    if document.ratios is None:
        return []
    unclassified = document.ratios.diagnostics.unclassified
    if not unclassified:
        return []
    total = sum((entry.value for entry in unclassified), Decimal(0))
    named = ', '.join((entry.label for entry in unclassified[:5]))
    return [Evidence(id='F-COVERAGE', kind=EvidenceKind.COVERAGE, label='Incomplete classification', value=str(total), detail=f'{len(unclassified)} line item(s) totalling {total} could not be classified and are excluded from the derived subtotals: {named}')]
__all__ = ['MAX_LINE_ITEM_FACTS', 'facts_for']
