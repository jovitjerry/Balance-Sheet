"""The ratio declarations must be internally consistent and self-documenting.

These tests never compute a ratio. They check that the *specification* holds
together: that every canonical label a formula names actually exists in Module
2's vocabulary, that a formula string says what its input specification does,
and that every ratio admits its own limitations. A declaration that has drifted
from the taxonomy would fail here rather than by silently contributing nothing
to a sum.
"""

from __future__ import annotations

from app.core.schemas import RatioBasis, RatioUnit
from app.modules.extraction import taxonomy
from app.modules.ratios import definitions
from app.modules.ratios.definitions import (
    DEFINITIONS,
    InputKind,
    InputSpec,
    Operation,
)

# The seven the project committed to. Balance Sheet only: anything needing an
# Income Statement or a Cash Flow Statement is out of scope, and a new name
# appearing here without a scope decision is exactly what this pins down.
EXPECTED = (
    "current_ratio",
    "quick_ratio",
    "cash_ratio",
    "debt_to_equity",
    "debt_ratio",
    "equity_ratio",
    "working_capital",
)


def _labels(spec: InputSpec) -> set[str]:
    """Every canonical label this specification names, including its base's."""
    named = set(spec.include) | set(spec.subtract)
    if spec.base is not None:
        named |= _labels(spec.base)
    return named


def _specs() -> list[InputSpec]:
    return [spec for definition in DEFINITIONS for spec in (definition.left, definition.right)]


class TestTheSetIsClosed:
    def test_exactly_the_seven_balance_sheet_ratios(self) -> None:
        assert definitions.names() == EXPECTED

    def test_no_ratio_needs_a_statement_this_project_does_not_read(self) -> None:
        """An Income Statement term in a formula means the scope line moved.

        Revenue, profit and cash flow do not appear on a Balance Sheet, so a
        formula mentioning one cannot be computed from what this system holds -
        and would have to fabricate the missing side.
        """
        forbidden = (
            "revenue",
            "sales",
            "profit",
            "income",
            "ebit",
            "cost of goods",
            "cash flow",
            "turnover",
            "interest expense",
        )
        for definition in DEFINITIONS:
            formula = definition.formula.lower()
            for term in forbidden:
                assert term not in formula, (
                    f"{definition.name} names {term!r}, which is not on a Balance Sheet"
                )

    def test_every_name_is_unique(self) -> None:
        assert len(definitions.names()) == len(set(definitions.names()))

    def test_get_returns_the_declaration_and_none_for_a_stranger(self) -> None:
        assert definitions.get("current_ratio") is DEFINITIONS[0]
        assert definitions.get("return_on_equity") is None


class TestEveryLabelExistsInTheTaxonomy:
    """Module 3 names canonical concepts. Module 2 owns what they are."""

    def test_named_labels_are_real_categories(self) -> None:
        for spec in _specs():
            for label in _labels(spec):
                assert taxonomy.get(label) is not None, (
                    f"{spec.name} names {label!r}, which is not in the taxonomy"
                )

    def test_named_labels_fit_the_section_they_are_used_in(self) -> None:
        """A whitelist may not name a category from another part of the sheet."""
        for spec in _specs():
            if spec.section is None:
                continue
            for label in spec.include:
                category = taxonomy.get(label)
                assert category is not None
                assert category.section is spec.section, (
                    f"{spec.name} includes {label!r}, which is not a "
                    f"{spec.section.value} category"
                )

    def test_quick_assets_subtracts_only_current_assets(self) -> None:
        """Subtracting a non-current category would silently corrupt the numerator."""
        for label in definitions.QUICK_ASSETS.subtract:
            category = taxonomy.get(label)
            assert category is not None
            assert category.section is taxonomy.Section.ASSETS
            assert category.subsection is taxonomy.Subsection.CURRENT

    def test_module_3_names_no_synonym(self) -> None:
        """Only canonical labels appear here - never a printed wording.

        "Trade Debtors" belongs to Module 2. If a synonym ever reaches this
        file, the vocabulary has a second half-copy that will drift.
        """
        canonical = set(taxonomy.labels())
        for spec in _specs():
            assert _labels(spec) <= canonical


class TestSpecificationsMatchTheirFormulas:
    def test_a_subtracted_label_is_named_in_the_formula(self) -> None:
        """The prose and the computation must describe the same subtraction."""
        quick = definitions.get("quick_ratio")
        assert quick is not None
        for label in quick.left.subtract:
            words = label.replace("_", " ")
            assert words in quick.formula.lower(), (
                f"quick_ratio subtracts {label!r} without saying so in its formula"
            )

    def test_composites_have_a_base_and_sums_do_not(self) -> None:
        for spec in _specs():
            if spec.kind is InputKind.COMPOSITE:
                assert spec.base is not None
                assert spec.subtract
            else:
                assert spec.base is None
                assert not spec.subtract

    def test_section_totals_name_a_section_and_nothing_else(self) -> None:
        for spec in _specs():
            if spec.kind is not InputKind.SECTION_TOTAL:
                continue
            assert spec.section is not None
            assert spec.subsection is None
            assert not spec.include

    def test_derived_sums_name_where_to_look(self) -> None:
        for spec in _specs():
            if spec.kind is InputKind.DERIVED_SUM:
                assert spec.section is not None

    def test_basis_follows_from_kind(self) -> None:
        assert definitions.TOTAL_ASSETS.basis is RatioBasis.SECTION_TOTAL
        assert definitions.CURRENT_ASSETS.basis is RatioBasis.DERIVED_SUM
        assert definitions.QUICK_ASSETS.basis is RatioBasis.COMPOSITE


class TestUnitsAndOperations:
    def test_working_capital_is_money_and_is_a_subtraction(self) -> None:
        working = definitions.get("working_capital")
        assert working is not None
        assert working.unit is RatioUnit.CURRENCY
        assert working.operation is Operation.SUBTRACT

    def test_every_other_ratio_is_a_dimensionless_quotient(self) -> None:
        for definition in DEFINITIONS:
            if definition.name == "working_capital":
                continue
            assert definition.unit is RatioUnit.RATIO
            assert definition.operation is Operation.DIVIDE

    def test_the_three_liquidity_ratios_share_a_denominator(self) -> None:
        """Comparing them only means something if the denominator is identical."""
        for name in ("current_ratio", "quick_ratio", "cash_ratio"):
            definition = definitions.get(name)
            assert definition is not None
            assert definition.right is definitions.CURRENT_LIABILITIES

    def test_quick_assets_are_built_from_the_current_ratio_numerator(self) -> None:
        """This is what guarantees quick <= current on every document."""
        assert definitions.QUICK_ASSETS.base is definitions.CURRENT_ASSETS


class TestEveryRatioExplainsItself:
    """The report is generated from these fields, so they must carry weight."""

    def test_each_declares_a_formula_a_definition_and_its_limitations(self) -> None:
        for definition in DEFINITIONS:
            assert definition.formula.strip()
            assert len(definition.definition) > 60, definition.name
            assert len(definition.limitations) > 60, definition.name

    def test_each_admits_the_single_period_limitation(self) -> None:
        """Scope: one reporting period. No trend, no benchmark, ever."""
        for definition in DEFINITIONS:
            assert "single reporting period" in definition.limitations, definition.name

    def test_the_ratios_with_a_contested_definition_name_what_was_rejected(self) -> None:
        """A choice between accounting definitions is only made once if it is written down."""
        quick = definitions.get("quick_ratio")
        assert quick is not None
        assert "SUBTRACTIVE" in quick.definition
        assert "additive" in quick.definition

        for name in ("debt_to_equity", "debt_ratio"):
            definition = definitions.get(name)
            assert definition is not None
            assert "borrowings" in definition.definition


class TestVersioning:
    def test_the_spec_version_is_separate_from_the_taxonomy_version(self) -> None:
        """A formula change and a vocabulary change must be distinguishable."""
        assert definitions.RATIO_SPEC_VERSION
        assert definitions.RATIO_SPEC_VERSION.count(".") == 2

    def test_definitions_are_frozen(self) -> None:
        """Declarations are data. Nothing mutates them at runtime."""
        import dataclasses

        import pytest

        with pytest.raises(dataclasses.FrozenInstanceError):
            DEFINITIONS[0].name = "changed"  # type: ignore[misc]
