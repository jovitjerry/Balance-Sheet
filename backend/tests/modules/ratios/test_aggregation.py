"""Which figures a ratio is allowed to use, and where they come from.

This is the part of Module 3 that can be wrong in a way that still looks right,
so it is tested apart from any formula.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.schemas import ExtractionStatus, NormalizationStatus, RatioBasis
from app.modules.extraction.taxonomy import Section, Subsection
from app.modules.ratios import definitions
from app.modules.ratios.definitions import InputKind, InputSpec
from app.modules.ratios.aggregation import (
    REASON_MISSING_SECTION_TOTAL,
    REASON_NOT_EXTRACTED,
    REASON_NO_CLASSIFIED_INPUTS,
    WARNING_UNMAPPED_INPUTS,
    WARNING_UNPARSED_INPUTS,
    SheetIndex,
)
from tests.modules.ratios.fixtures import balanced_sheet, item, section, sheet


class TestClassification:
    def test_current_assets_sum_the_classified_leaves(self) -> None:
        index = SheetIndex(balanced_sheet())
        result = index.resolve(definitions.CURRENT_ASSETS)

        assert result.value == Decimal("850000")
        assert result.basis is RatioBasis.DERIVED_SUM
        assert len(result.inputs) == 4

    def test_the_canonical_category_classifies_not_the_printed_heading(self) -> None:
        """A sheet with no current/non-current headings still yields subtotals.

        This is the whole reason classification reads the taxonomy rather than
        LineItem.subsection: single-column Balance Sheets routinely print only
        ASSETS / LIABILITIES / EQUITY, and heading-based classification would
        compute nothing at all on them.
        """
        no_headings = sheet(
            assets=section(
                "2300000",
                [
                    item("Cash and cash equivalents", "300000",
                         "cash_and_cash_equivalents", subsection=None),
                    item("Property, plant and equipment", "2000000",
                         "property_plant_and_equipment", subsection=None),
                ],
            ),
            liabilities=section(
                "1350000",
                [
                    item("Trade payables", "350000", "trade_payables", subsection=None),
                    item("Long-term borrowings", "1000000", "long_term_borrowings",
                         subsection=None),
                ],
            ),
            equity=section("950000", []),
        )
        index = SheetIndex(no_headings)

        assert index.resolve(definitions.CURRENT_ASSETS).value == Decimal("300000")
        assert index.resolve(definitions.CURRENT_LIABILITIES).value == Decimal("350000")

    def test_a_line_item_carries_its_printed_label_into_the_inputs(self) -> None:
        """Traceability: the canonical concept never replaces what was printed."""
        debtors = sheet(
            assets=section(
                "280000",
                [item("Trade Debtors", "280000", "trade_receivables", subsection="current")],
            ),
            liabilities=section("0", []),
            equity=section("0", []),
        )
        [only] = SheetIndex(debtors).resolve(definitions.CURRENT_ASSETS).inputs

        assert only.canonical_label == "trade_receivables"
        assert only.label == "Trade Debtors"
        assert only.source is not None
        assert only.source.page_index == 0

    def test_an_unnormalized_line_is_never_classified(self) -> None:
        index = SheetIndex(
            sheet(
                assets=section(
                    "95000",
                    [item("Sundry Balances", "95000", None, subsection="current")],
                ),
                liabilities=section("0", []),
                equity=section("0", []),
            )
        )
        result = index.resolve(definitions.CURRENT_ASSETS)

        assert result.value is None
        assert result.reason == REASON_NO_CLASSIFIED_INPUTS
        assert [entry.label for entry in result.excluded] == ["Sundry Balances"]

    def test_a_label_outside_this_taxonomy_version_is_not_classified(self) -> None:
        """A mapping made under a vocabulary this engine does not have is not a mapping."""
        stale = sheet(
            assets=section(
                "100",
                [item("Crypto holdings", "100", "digital_assets", subsection="current")],
            ),
            liabilities=section("0", []),
            equity=section("0", []),
        )
        result = SheetIndex(stale).resolve(definitions.CURRENT_ASSETS)

        assert result.value is None
        assert [entry.label for entry in result.excluded] == ["Crypto holdings"]


class TestNoDoubleCounting:
    def test_a_total_line_reaching_aggregation_is_refused_loudly(self) -> None:
        """The guard that catches a Module 2 regression before it inflates a section.

        Summing a subtotal alongside the items it summarises roughly doubles a
        section, which is a plausible-looking number nobody checks by hand.
        """
        corrupt = sheet(
            assets=section(
                "850000",
                [
                    item("Inventory", "350000", "inventory", subsection="current"),
                    item("Total Current Assets", "850000", "other_current_assets",
                         subsection="current"),
                ],
            ),
            liabilities=section("0", []),
            equity=section("0", []),
        )
        with pytest.raises(AssertionError, match="Total Current Assets"):
            SheetIndex(corrupt)

    def test_the_section_total_is_not_among_the_summed_items(self) -> None:
        """Grand totals live outside line_items, so they cannot be swept into a sum."""
        index = SheetIndex(balanced_sheet())
        current = index.resolve(definitions.CURRENT_ASSETS)

        assert Decimal("2300000") not in [entry.value for entry in current.inputs]
        assert current.value == Decimal("850000")

    def test_duplicate_canonical_labels_are_summed_and_flagged(self) -> None:
        """Two printed lines are two figures. Reported, never de-duplicated."""
        duplicated = sheet(
            assets=section(
                "400000",
                [
                    item("Trade receivables", "280000", "trade_receivables",
                         subsection="current", row=1),
                    item("Receivables from related parties", "120000",
                         "trade_receivables", subsection="current", row=2),
                ],
            ),
            liabilities=section("0", []),
            equity=section("0", []),
        )
        index = SheetIndex(duplicated)

        assert index.resolve(definitions.CURRENT_ASSETS).value == Decimal("400000")
        assert index.duplicate_canonical_labels() == {"trade_receivables": 2}


class TestSectionTotals:
    def test_a_grand_total_comes_from_module_1_not_from_the_leaves(self) -> None:
        """Even when the leaves do not add up to it.

        Module 1 read this figure off the page and checked the accounting
        equation against it. Re-deriving it here would replace a validated
        number with one whose accuracy depends on extraction completeness.
        """
        incomplete = sheet(
            assets=section(
                "2300000",
                [item("Inventory", "350000", "inventory", subsection="current")],
            ),
            liabilities=section("1350000", []),
            equity=section("950000", []),
        )
        result = SheetIndex(incomplete).resolve(definitions.TOTAL_ASSETS)

        assert result.value == Decimal("2300000")
        assert result.basis is RatioBasis.SECTION_TOTAL

    def test_a_section_total_carries_its_printed_label(self) -> None:
        [only] = SheetIndex(balanced_sheet()).resolve(definitions.TOTAL_ASSETS).inputs
        assert only.label == "TOTAL ASSETS"
        assert only.canonical_label is None

    def test_a_section_total_is_unaffected_by_unmapped_line_items(self) -> None:
        """The asymmetry that keeps leverage ratios alive with the model switched off."""
        unmapped = sheet(
            assets=section(
                "2300000",
                [item("Assorted holdings", "2300000", None, subsection="current")],
            ),
            liabilities=section("1350000", []),
            equity=section("950000", []),
        )
        index = SheetIndex(unmapped)

        assert index.resolve(definitions.TOTAL_ASSETS).value == Decimal("2300000")
        assert index.resolve(definitions.TOTAL_ASSETS).warnings == []
        assert index.resolve(definitions.CURRENT_ASSETS).value is None


class TestCoverage:
    def test_an_unmapped_line_with_a_figure_is_named_and_totalled(self) -> None:
        partial = sheet(
            assets=section(
                "945000",
                [
                    item("Inventory", "350000", "inventory", subsection="current"),
                    item("Sundry Balances", "95000", None, subsection="current"),
                ],
            ),
            liabilities=section("0", []),
            equity=section("0", []),
        )
        result = SheetIndex(partial).resolve(definitions.CURRENT_ASSETS)

        assert result.value == Decimal("350000")
        assert WARNING_UNMAPPED_INPUTS in result.warnings
        assert result.excluded_value == Decimal("95000")
        assert [entry.label for entry in result.excluded] == ["Sundry Balances"]

    def test_a_printed_heading_narrows_which_quantities_a_line_could_join(self) -> None:
        """An unmapped line printed under Non-Current Assets is not a current asset.

        The heading never places a figure into a sum - it only rules a line out
        of an exclusion list it could not have belonged to. Without this, every
        unmappable non-current line would make every liquidity ratio partial.
        """
        mixed = sheet(
            assets=section(
                "1550000",
                [
                    item("Inventory", "350000", "inventory", subsection="current"),
                    item("Assorted fixed assets", "1200000", None,
                         subsection="non_current"),
                ],
            ),
            liabilities=section("0", []),
            equity=section("0", []),
        )
        result = SheetIndex(mixed).resolve(definitions.CURRENT_ASSETS)

        assert result.value == Decimal("350000")
        assert result.excluded == []
        assert result.warnings == []

    def test_an_unmapped_line_with_no_heading_is_treated_as_possible(self) -> None:
        """Nothing rules it out, so it has to be reported as possibly missing."""
        unknown = sheet(
            assets=section(
                "445000",
                [
                    item("Inventory", "350000", "inventory", subsection="current"),
                    item("Sundry Balances", "95000", None, subsection=None),
                ],
            ),
            liabilities=section("0", []),
            equity=section("0", []),
        )
        result = SheetIndex(unknown).resolve(definitions.CURRENT_ASSETS)
        assert [entry.label for entry in result.excluded] == ["Sundry Balances"]

    def test_an_unparsed_figure_is_excluded_and_warned_about(self) -> None:
        unparsed = sheet(
            assets=section(
                "350000",
                [
                    item("Inventory", "350000", "inventory", subsection="current"),
                    item("Prepaid expenses", None, "prepaid_expenses",
                         subsection="current",
                         extraction=ExtractionStatus.UNPARSED_VALUE),
                ],
            ),
            liabilities=section("0", []),
            equity=section("0", []),
        )
        result = SheetIndex(unparsed).resolve(definitions.CURRENT_ASSETS)

        assert result.value == Decimal("350000")
        assert WARNING_UNPARSED_INPUTS in result.warnings
        assert result.excluded_value is None

    def test_a_known_category_narrows_an_unparsed_lines_reach(self) -> None:
        """A line that mapped but whose figure would not parse is not a mystery.

        Its category says exactly which quantities the missing number would
        have affected, so it must not make every other one report itself
        incomplete. Here the unreadable figure is a non-current asset, and the
        current-asset sum is unaffected by it.
        """
        unparsed = sheet(
            assets=section(
                "1550000",
                [
                    item("Inventory", "350000", "inventory", subsection="current"),
                    item("Property, plant and equipment", None,
                         "property_plant_and_equipment", subsection=None,
                         extraction=ExtractionStatus.UNPARSED_VALUE),
                ],
            ),
            liabilities=section("0", []),
            equity=section("0", []),
        )
        index = SheetIndex(unparsed)

        current = index.resolve(definitions.CURRENT_ASSETS)
        assert current.value == Decimal("350000")
        assert current.warnings == []

        # The quantity it would have belonged to still reports the gap.
        non_current = index.resolve(
            InputSpec(
                "Non-Current Assets",
                InputKind.DERIVED_SUM,
                section=Section.ASSETS,
                subsection=Subsection.NON_CURRENT,
            )
        )
        assert WARNING_UNPARSED_INPUTS in non_current.warnings

    def test_a_needs_review_line_is_never_given_a_category(self) -> None:
        """Not other_*, not the heading's, not a guess. It is simply not classified."""
        review = sheet(
            assets=section(
                "95000",
                [
                    item("Miscellaneous Financial Assets", "95000", None,
                         status=NormalizationStatus.NEEDS_REVIEW, subsection="current")
                ],
            ),
            liabilities=section("0", []),
            equity=section("0", []),
        )
        index = SheetIndex(review)

        assert index.classified == []
        assert index.resolve(definitions.CURRENT_ASSETS).value is None


class TestComposites:
    def test_quick_assets_are_current_assets_less_inventory_and_prepaid(self) -> None:
        index = SheetIndex(balanced_sheet())
        quick = index.resolve(definitions.QUICK_ASSETS)

        assert quick.value == Decimal("500000")
        assert quick.basis is RatioBasis.COMPOSITE
        assert "inventory" not in [entry.canonical_label for entry in quick.inputs]

    def test_the_inputs_list_shows_exactly_what_was_counted(self) -> None:
        quick = SheetIndex(balanced_sheet()).resolve(definitions.QUICK_ASSETS)
        assert sum(entry.value for entry in quick.inputs) == quick.value

    def test_an_absent_subtrahend_subtracts_nothing(self) -> None:
        """A sheet with no prepaid expenses genuinely has none to remove."""
        no_prepaid = sheet(
            assets=section(
                "125000",
                [item("Cash and cash equivalents", "125000",
                      "cash_and_cash_equivalents", subsection="current")],
            ),
            liabilities=section("0", []),
            equity=section("0", []),
        )
        assert SheetIndex(no_prepaid).resolve(
            definitions.QUICK_ASSETS
        ).value == Decimal("125000")

    def test_all_inventory_gives_zero_quick_assets_not_an_absent_one(self) -> None:
        """Zero is a real answer here: the current assets were classified."""
        all_stock = sheet(
            assets=section(
                "350000",
                [item("Inventory", "350000", "inventory", subsection="current")],
            ),
            liabilities=section("0", []),
            equity=section("0", []),
        )
        result = SheetIndex(all_stock).resolve(definitions.QUICK_ASSETS)

        assert result.value == Decimal("0")
        assert result.reason is None

    def test_a_composite_is_unavailable_when_its_base_is(self) -> None:
        empty = sheet(
            assets=section("0", []), liabilities=section("0", []), equity=section("0", [])
        )
        assert SheetIndex(empty).resolve(definitions.QUICK_ASSETS).value is None


class TestCashAssetsAreAWhitelist:
    def test_only_cash_and_short_term_investments_count(self) -> None:
        result = SheetIndex(balanced_sheet()).resolve(definitions.CASH_ASSETS)
        assert result.value == Decimal("125000")

    def test_an_absent_addend_is_absent_not_zero(self) -> None:
        """Reporting zero cash for a document we failed to read would invent insolvency."""
        no_cash = sheet(
            assets=section(
                "350000",
                [item("Inventory", "350000", "inventory", subsection="current")],
            ),
            liabilities=section("0", []),
            equity=section("0", []),
        )
        result = SheetIndex(no_cash).resolve(definitions.CASH_ASSETS)

        assert result.value is None
        assert result.reason == REASON_NO_CLASSIFIED_INPUTS


class TestMissingData:
    def test_no_line_items_at_all_says_so_distinctly(self) -> None:
        """"Module 2 never ran" is a different failure from "nothing mapped"."""
        empty = sheet(
            assets=section("2300000", []),
            liabilities=section("1350000", []),
            equity=section("950000", []),
        )
        result = SheetIndex(empty).resolve(definitions.CURRENT_ASSETS)
        assert result.reason == REASON_NOT_EXTRACTED

    def test_a_missing_section_total_is_reported_as_such(self) -> None:
        index = SheetIndex(balanced_sheet())
        index.totals[definitions.TOTAL_EQUITY.section] = None  # type: ignore[index]

        result = index.resolve(definitions.TOTAL_EQUITY)
        assert result.value is None
        assert result.reason == REASON_MISSING_SECTION_TOTAL


class TestDiagnostics:
    def test_unclassified_lines_are_listed_with_their_figures(self) -> None:
        partial = sheet(
            assets=section(
                "95000", [item("Sundry Balances", "95000", None, subsection="current")]
            ),
            liabilities=section("0", []),
            equity=section("0", []),
        )
        [only] = SheetIndex(partial).unclassified_inputs()

        assert only.label == "Sundry Balances"
        assert only.value == Decimal("95000")
        assert only.canonical_label is None

    def test_reconciliation_difference_is_carried_through_per_section(self) -> None:
        """How far the derived level and the printed level disagree."""
        short = sheet(
            assets=section(
                "2300000",
                [item("Inventory", "350000", "inventory", subsection="current")],
            ),
            liabilities=section("0", []),
            equity=section("0", []),
        )
        assert SheetIndex(short).reconciliation_difference()["assets"] == Decimal("1950000")

    def test_a_complete_sheet_reports_nothing_unclassified(self) -> None:
        index = SheetIndex(balanced_sheet())
        assert index.unclassified_inputs() == []
        assert index.duplicate_canonical_labels() == {}
