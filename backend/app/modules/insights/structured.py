"""The authoritative half of retrieval: facts, not similarity.

Everything here was computed by deterministic code in Modules 1-3 and is read
straight off the loaded document. No database round trip, no embedding, no
model, no ranking - so this path costs nothing and is always taken. That is
what makes the vector query the only retrieval decision with a real price.

**Precision is the whole point.** A figure retrieved here is the exact
``Decimal`` Module 2 parsed, carrying the page, row and column it was printed
at. Semantic search over the same page would return the same number as fuzzy
prose, less reliably, having paid for an embedding to do it.

The facts are handed to the model as its *only* permitted source of figures,
and the same set becomes the allowed set the numeric verifier checks the answer
against - so anything omitted here is a figure the model may not state.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.schemas import (
    BalanceSheetDocument,
    BalanceSheetSection,
    Evidence,
    EvidenceKind,
    RatioResult,
    RatioStatus,
)
from app.modules.insights.routing import RouteDecision
from app.modules.ratios import definitions

# A whole Balance Sheet's facts - three totals, ~15 line items, seven ratios -
# is around 25 lines, which fits the context window comfortably. The cap exists
# for an unusually long filing, and because an unbounded prompt is a bug
# waiting for the document that triggers it.
MAX_LINE_ITEM_FACTS = 40

_SECTION_LABELS: dict[str, str] = {
    "assets": "Total assets",
    "liabilities": "Total liabilities",
    "equity": "Total equity",
}


def facts_for(
    document: BalanceSheetDocument, *, decision: RouteDecision
) -> list[Evidence]:
    """Every authoritative figure worth showing, most relevant first.

    Pure and synchronous: the document is already in memory, so there is
    nothing to await and nothing to fail. ``decision`` decides only the
    *ordering* - what the question named comes first - not what is included.

    Including the whole sheet rather than a relevant subset is deliberate.
    "Which is the largest asset?" cannot be answered from a selection, and a
    figure left out is a figure the verifier will later refuse, so a narrow
    context would produce refusals on perfectly answerable questions.
    """
    facts: list[Evidence] = []

    if document.equation_check is not None:
        check = document.equation_check
        facts.append(
            Evidence(
                id="F0",
                kind=EvidenceKind.EQUATION,
                label="Accounting equation",
                value=str(check.total_assets),
                detail=(
                    f"Total assets {check.total_assets} = total liabilities "
                    f"{check.total_liabilities} + total equity {check.total_equity}; "
                    f"{'balances' if check.balanced else 'does NOT balance'}"
                ),
            )
        )

    extracted = document.extracted
    if extracted is None:
        return facts

    index = 1
    for field_name, label in _SECTION_LABELS.items():
        part: BalanceSheetSection = getattr(extracted, field_name)
        facts.append(
            Evidence(
                id=f"F{index}",
                kind=EvidenceKind.SECTION_TOTAL,
                label=label,
                value=str(part.total),
                detail=part.total_label,
                source=part.total_source,
            )
        )
        index += 1

    for item in _ordered_line_items(extracted, decision)[:MAX_LINE_ITEM_FACTS]:
        facts.append(
            Evidence(
                id=f"F{index}",
                kind=EvidenceKind.LINE_ITEM,
                label=item.label,
                value=str(item.value) if item.value is not None else None,
                detail=_line_detail(item),
                source=item.source,
            )
        )
        index += 1

    facts.extend(_ratio_facts(document, decision))
    facts.extend(_coverage_facts(document))
    return facts


def _ordered_line_items(extracted, decision: RouteDecision):
    """Line items with the ones the question named first.

    Only the order changes. A question about inventory still sees every other
    line, because "is that a lot?" is unanswerable without them.
    """
    named_labels = set(decision.matched_labels)
    named_concepts = set(decision.matched_concepts)

    items = [
        item
        for field_name in ("assets", "liabilities", "equity")
        for item in getattr(extracted, field_name).line_items
    ]

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
    """What this line was understood to be, and where it sits.

    The canonical concept is recorded beside the printed label rather than in
    place of it, so "Trade Debtors" stays visible as what the document actually
    said - the same rule Module 2 follows.
    """
    parts: list[str] = []
    canonical = _canonical_of(item)
    if canonical:
        parts.append(canonical)
    elif item.normalization is not None:
        parts.append(f"not classified ({item.normalization.status.value})")
    if item.subsection:
        parts.append(item.subsection)
    # ASCII separator deliberately: this string goes into a prompt, and a
    # non-ASCII glyph is one more thing that can arrive mangled on a Windows
    # console or in a differently-encoded log.
    return ", ".join(parts) if parts else None


def _ratio_facts(
    document: BalanceSheetDocument, decision: RouteDecision
) -> list[Evidence]:
    """The computed ratios, including the ones that could not be computed.

    An unavailable ratio is reported with its reason rather than omitted.
    Leaving it out would read as "no issue here"; inventing a number would be
    worse. "Unavailable, because no current liabilities could be classified" is
    the honest answer and the only one the document supports.
    """
    if document.ratios is None:
        return []

    named = set(decision.matched_concepts)
    ordered = sorted(
        document.ratios.ratios, key=lambda result: 0 if result.name in named else 1
    )

    return [
        Evidence(
            id=f"R{position}",
            kind=EvidenceKind.RATIO,
            label=result.name,
            value=str(result.value) if result.value is not None else None,
            detail=_ratio_detail(result),
        )
        for position, result in enumerate(ordered, start=1)
    ]


def _ratio_detail(result: RatioResult) -> str:
    """Formula, operands, status and the caveat Module 3 wrote for this ratio.

    The limitation comes from ``definitions.py`` so the model explains a ratio
    using the project's own stated caveat rather than whatever it believes
    about the ratio in general.
    """
    parts = [result.formula]

    if result.status is RatioStatus.UNAVAILABLE:
        parts.append(f"UNAVAILABLE ({result.reason})")
    else:
        if result.numerator is not None and result.denominator is not None:
            parts.append(
                f"numerator {result.numerator}, denominator {result.denominator}"
            )
        if result.status is not RatioStatus.OK:
            parts.append(f"status {result.status.value}")
        if result.warnings:
            parts.append("warnings: " + ", ".join(result.warnings))

    definition = definitions.get(result.name)
    if definition is not None:
        parts.append("limitation: " + _first_sentence(definition.limitations))
    return "; ".join(parts)


def _first_sentence(text: str) -> str:
    """The headline caveat only - the full text would crowd out the facts."""
    sentence, _, _ = text.partition(". ")
    return sentence.strip().rstrip(".") + "."


def _coverage_facts(document: BalanceSheetDocument) -> list[Evidence]:
    """How much of the sheet nobody could classify.

    Surfaced so an answer can admit an incomplete picture. It is also the only
    signal available for the failure this system cannot detect - a line mapped
    confidently to the wrong category leaves no other trace.
    """
    if document.ratios is None:
        return []

    unclassified = document.ratios.diagnostics.unclassified
    if not unclassified:
        return []

    total = sum((entry.value for entry in unclassified), Decimal(0))
    named = ", ".join(entry.label for entry in unclassified[:5])
    return [
        Evidence(
            id="F-COVERAGE",
            kind=EvidenceKind.COVERAGE,
            label="Incomplete classification",
            value=str(total),
            detail=(
                f"{len(unclassified)} line item(s) totalling {total} could not be "
                f"classified and are excluded from the derived subtotals: {named}"
            ),
        )
    ]


__all__ = ["MAX_LINE_ITEM_FACTS", "facts_for"]
