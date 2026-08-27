"""Gathering the authoritative facts, from data already in memory.

No I/O, no model, no approximation. Every figure here was computed by
deterministic code in Modules 1-3 and carries the source reference it was read
from, so this path answers a financial question exactly rather than
approximately - which is why it always runs, and why the vector query is the
only retrieval decision with a real cost.
"""

from __future__ import annotations

import inspect
from decimal import Decimal

from app.core.schemas import EvidenceKind
from app.modules.insights.routing import route
from app.modules.insights.structured import facts_for
from tests.modules.insights.fixtures import analyzed_document


def _by_kind(facts, kind: EvidenceKind):
    return [fact for fact in facts if fact.kind is kind]


def _find(facts, label: str):
    return next((fact for fact in facts if fact.label == label), None)


class TestItGathersWhatModules1To3Stored:
    def test_the_three_section_totals(self) -> None:
        facts = facts_for(analyzed_document(), decision=route("What are total assets?"))
        totals = {fact.label: fact.value for fact in _by_kind(facts, EvidenceKind.SECTION_TOTAL)}

        assert totals["Total assets"] == "2300000"
        assert totals["Total liabilities"] == "1350000"
        assert totals["Total equity"] == "950000"

    def test_every_line_item(self) -> None:
        """All of them, so "which is largest?" is answerable at all."""
        facts = facts_for(analyzed_document(), decision=route("What is the largest asset?"))
        labels = {fact.label for fact in _by_kind(facts, EvidenceKind.LINE_ITEM)}

        assert "Inventory" in labels
        assert "Property, plant and equipment" in labels
        assert len(labels) == 14

    def test_the_seven_ratios(self) -> None:
        facts = facts_for(analyzed_document(), decision=route("Is it liquid?"))
        ratios = {fact.label: fact.value for fact in _by_kind(facts, EvidenceKind.RATIO)}

        assert len(ratios) == 7
        assert ratios["current_ratio"] == "1.307692"
        assert ratios["working_capital"] == "200000"

    def test_the_equation_check(self) -> None:
        facts = facts_for(analyzed_document(), decision=route("Does it balance?"))
        [equation] = _by_kind(facts, EvidenceKind.EQUATION)

        assert "2300000" in (equation.value or "")
        assert equation.detail is not None


class TestFiguresAreExactStrings:
    def test_money_is_never_a_float(self) -> None:
        """A JSON number is an IEEE double, which is what Decimal exists to avoid."""
        facts = facts_for(analyzed_document(), decision=route("How much inventory?"))
        for fact in facts:
            assert fact.value is None or isinstance(fact.value, str)

    def test_a_value_is_not_reformatted(self) -> None:
        inventory = _find(
            facts_for(analyzed_document(), decision=route("How much inventory?")),
            "Inventory",
        )
        assert inventory is not None
        assert inventory.value == "350000"
        assert Decimal(inventory.value) == Decimal("350000")


class TestTraceability:
    def test_a_line_item_carries_its_source_reference(self) -> None:
        inventory = _find(
            facts_for(analyzed_document(), decision=route("How much inventory?")),
            "Inventory",
        )
        assert inventory is not None
        assert inventory.source is not None
        assert inventory.source.page_index == 0
        assert inventory.source.row is not None

    def test_a_line_item_names_its_canonical_concept(self) -> None:
        """The printed label is what is shown; the concept is what it maps to."""
        inventory = _find(
            facts_for(analyzed_document(), decision=route("How much inventory?")),
            "Inventory",
        )
        assert inventory is not None
        assert "inventory" in (inventory.detail or "")

    def test_a_ratio_carries_its_formula_and_operands(self) -> None:
        current = _find(
            facts_for(analyzed_document(), decision=route("What is the current ratio?")),
            "current_ratio",
        )
        assert current is not None
        assert "Current Assets / Current Liabilities" in (current.detail or "")
        assert "850000" in (current.detail or "")
        assert "650000" in (current.detail or "")

    def test_every_fact_has_a_unique_citation_tag(self) -> None:
        facts = facts_for(analyzed_document(), decision=route("Tell me everything"))
        tags = [fact.id for fact in facts]
        assert len(tags) == len(set(tags))


class TestUnavailableRatiosAreStatedNotHidden:
    def test_an_uncomputable_ratio_says_why(self) -> None:
        """Silence would read as "no problem"; a number would be a fabrication."""
        document = analyzed_document(
            labels={"assets": [("Assorted holdings", "2300000")]}
        )
        current = _find(
            facts_for(document, decision=route("What is the current ratio?")),
            "current_ratio",
        )

        assert current is not None
        assert current.value is None
        assert "unavailable" in (current.detail or "").lower()
        assert "no_classified_inputs" in (current.detail or "")

    def test_the_leverage_ratios_survive_an_unnormalizable_sheet(self) -> None:
        """They rest on Module 1's printed totals, not on normalization."""
        document = analyzed_document(
            labels={"assets": [("Assorted holdings", "2300000")]}
        )
        debt = _find(
            facts_for(document, decision=route("How much debt?")), "debt_ratio"
        )
        assert debt is not None
        assert debt.value == "0.586957"


class TestCoverageIsDisclosed:
    def test_unclassified_lines_are_reported(self) -> None:
        """The model must be able to say the picture is incomplete."""
        document = analyzed_document(
            labels={"assets": [("Sundry Balances", "95000")]}
        )
        coverage = _by_kind(
            facts_for(document, decision=route("What is the current ratio?")),
            EvidenceKind.COVERAGE,
        )
        assert coverage
        assert coverage[0].detail is not None
        assert "Sundry Balances" in coverage[0].detail
        assert coverage[0].value == "95000"

    def test_a_complete_sheet_reports_no_coverage_problem(self) -> None:
        facts = facts_for(analyzed_document(), decision=route("Anything wrong?"))
        assert _by_kind(facts, EvidenceKind.COVERAGE) == []


class TestRelevanceOrdering:
    def test_the_named_concept_comes_first_among_line_items(self) -> None:
        """So that truncating a long sheet drops the least relevant, not the point."""
        facts = facts_for(
            analyzed_document(), decision=route("How much inventory is there?")
        )
        items = _by_kind(facts, EvidenceKind.LINE_ITEM)
        assert items[0].label == "Inventory"

    def test_the_named_ratio_comes_first_among_ratios(self) -> None:
        facts = facts_for(
            analyzed_document(), decision=route("What is the debt to equity ratio?")
        )
        ratios = _by_kind(facts, EvidenceKind.RATIO)
        assert ratios[0].label == "debt_to_equity"


class TestPurity:
    def test_it_is_synchronous(self) -> None:
        assert not inspect.iscoroutinefunction(facts_for)

    def test_it_takes_no_database_or_provider(self) -> None:
        parameters = set(inspect.signature(facts_for).parameters)
        assert parameters == {"document", "decision"}

    def test_it_does_not_mutate_the_document(self) -> None:
        import copy

        document = analyzed_document()
        before = copy.deepcopy(document)
        facts_for(document, decision=route("Anything"))
        assert document == before

    def test_a_document_without_ratios_still_yields_its_totals(self) -> None:
        """Module 3 not having run is not a reason to answer nothing."""
        document = analyzed_document().model_copy(update={"ratios": None})
        facts = facts_for(document, decision=route("What are total assets?"))

        assert _by_kind(facts, EvidenceKind.SECTION_TOTAL)
        assert _by_kind(facts, EvidenceKind.RATIO) == []
