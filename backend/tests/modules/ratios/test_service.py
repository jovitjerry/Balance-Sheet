"""Computing the ratios: values, refusals, precision and traceability."""

from __future__ import annotations

import copy
import inspect
from decimal import Decimal

from app.core.schemas import RatioBasis, RatioStatus, RatioUnit
from app.modules.extraction.taxonomy import TAXONOMY_VERSION
from app.modules.ratios import definitions
from app.modules.ratios.aggregation import (
    REASON_NOT_EXTRACTED,
    REASON_NO_CLASSIFIED_INPUTS,
    REASON_ZERO_DENOMINATOR,
    REASONS,
    WARNING_NEGATIVE_DENOMINATOR,
    WARNING_NEGATIVE_RESULT,
    WARNING_UNMAPPED_INPUTS,
    WARNINGS,
)
from app.modules.ratios.service import RATIO_DECIMAL_PLACES, compute_ratios
from tests.modules.ratios.fixtures import balanced_sheet, item, section, sheet


def _value(result, name: str) -> Decimal | None:
    ratio = result.get(name)
    assert ratio is not None, name
    return ratio.value


class TestKnownValues:
    """Hand-derived from the fixture. No model computed or checked any of these."""

    def test_every_ratio_on_a_complete_sheet(self) -> None:
        result = compute_ratios(balanced_sheet())

        assert _value(result, "current_ratio") == Decimal("1.307692")
        assert _value(result, "quick_ratio") == Decimal("0.769231")
        assert _value(result, "cash_ratio") == Decimal("0.192308")
        assert _value(result, "debt_to_equity") == Decimal("1.421053")
        assert _value(result, "debt_ratio") == Decimal("0.586957")
        assert _value(result, "equity_ratio") == Decimal("0.413043")
        assert _value(result, "working_capital") == Decimal("200000")

    def test_all_seven_are_produced(self) -> None:
        result = compute_ratios(balanced_sheet())
        assert [ratio.name for ratio in result.ratios] == list(definitions.names())

    def test_a_complete_sheet_reports_every_ratio_ok(self) -> None:
        for ratio in compute_ratios(balanced_sheet()).ratios:
            assert ratio.status is RatioStatus.OK, ratio.name
            assert ratio.reason is None

    def test_debt_and_equity_ratios_sum_to_one_on_a_balanced_sheet(self) -> None:
        """A cross-check that catches a swapped numerator."""
        result = compute_ratios(balanced_sheet())
        total = _value(result, "debt_ratio") + _value(result, "equity_ratio")  # type: ignore[operator]
        assert total == Decimal("1.000000")

    def test_quick_never_exceeds_current(self) -> None:
        """Guaranteed by the subtractive definition sharing the current numerator."""
        result = compute_ratios(balanced_sheet())
        assert _value(result, "quick_ratio") <= _value(result, "current_ratio")  # type: ignore[operator]
        assert _value(result, "cash_ratio") <= _value(result, "quick_ratio")  # type: ignore[operator]


class TestWorkingCapital:
    def test_it_is_money_and_is_exact(self) -> None:
        working = compute_ratios(balanced_sheet()).get("working_capital")
        assert working is not None
        assert working.unit is RatioUnit.CURRENCY
        assert working.value == Decimal("200000")
        # Not quantized to six places: a rounded money figure would not tie
        # back to the sheet it came from.
        assert working.value == working.numerator - working.denominator  # type: ignore[operator]

    def test_negative_working_capital_is_reported_with_its_sign(self) -> None:
        tight = sheet(
            assets=section(
                "2300000",
                [item("Cash and cash equivalents", "300000",
                      "cash_and_cash_equivalents", subsection="current")],
            ),
            liabilities=section(
                "1350000",
                [item("Trade payables", "350000", "trade_payables", subsection="current")],
            ),
            equity=section("950000", []),
        )
        working = compute_ratios(tight).get("working_capital")
        assert working is not None
        assert working.value == Decimal("-50000")
        assert working.status is RatioStatus.OK
        assert WARNING_NEGATIVE_RESULT in working.warnings

    def test_zero_current_liabilities_still_gives_working_capital(self) -> None:
        """A subtraction has no denominator to be zero.

        The same sheet whose current *ratio* is unavailable still has a
        perfectly well-defined working capital, and reporting one without the
        other is the point of separating the two.
        """
        debt_free = sheet(
            assets=section(
                "125000",
                [item("Cash and cash equivalents", "125000",
                      "cash_and_cash_equivalents", subsection="current")],
            ),
            liabilities=section(
                "0", [item("Trade payables", "0", "trade_payables", subsection="current")]
            ),
            equity=section("125000", []),
        )
        result = compute_ratios(debt_free)

        working = result.get("working_capital")
        assert working is not None
        assert working.status is RatioStatus.OK
        assert working.value == Decimal("125000")

        current = result.get("current_ratio")
        assert current is not None
        assert current.status is RatioStatus.UNAVAILABLE
        assert current.reason == REASON_ZERO_DENOMINATOR


class TestZeroDenominator:
    def test_zero_current_liabilities_makes_the_current_ratio_unavailable(self) -> None:
        """Not infinity. A company with no current liabilities has no current ratio."""
        zero = sheet(
            assets=section(
                "125000",
                [item("Cash and cash equivalents", "125000",
                      "cash_and_cash_equivalents", subsection="current")],
            ),
            liabilities=section(
                "0", [item("Trade payables", "0", "trade_payables", subsection="current")]
            ),
            equity=section("125000", []),
        )
        current = compute_ratios(zero).get("current_ratio")
        assert current is not None
        assert current.status is RatioStatus.UNAVAILABLE
        assert current.value is None
        assert current.reason == REASON_ZERO_DENOMINATOR

    def test_the_resolved_side_is_still_reported(self) -> None:
        """"Current assets 125,000, denominator zero" beats a blank."""
        zero = sheet(
            assets=section(
                "125000",
                [item("Cash and cash equivalents", "125000",
                      "cash_and_cash_equivalents", subsection="current")],
            ),
            liabilities=section(
                "0", [item("Trade payables", "0", "trade_payables", subsection="current")]
            ),
            equity=section("125000", []),
        )
        current = compute_ratios(zero).get("current_ratio")
        assert current is not None
        assert current.numerator == Decimal("125000")
        assert len(current.numerator_inputs) == 1

    def test_zero_equity_makes_debt_to_equity_unavailable(self) -> None:
        wiped = sheet(
            assets=section("1350000", []),
            liabilities=section("1350000", []),
            equity=section("0", []),
        )
        ratio = compute_ratios(wiped).get("debt_to_equity")
        assert ratio is not None
        assert ratio.reason == REASON_ZERO_DENOMINATOR


class TestNegativeValues:
    def test_negative_equity_is_computed_not_clamped(self) -> None:
        """Hiding insolvency would be the worst thing this system could do."""
        insolvent = sheet(
            assets=section("500000", []),
            liabilities=section("800000", []),
            equity=section("-300000", []),
        )
        ratio = compute_ratios(insolvent).get("debt_to_equity")
        assert ratio is not None
        assert ratio.value == Decimal("-2.666667")
        assert ratio.status is RatioStatus.OK
        assert WARNING_NEGATIVE_DENOMINATOR in ratio.warnings
        assert WARNING_NEGATIVE_RESULT in ratio.warnings

    def test_an_equity_ratio_above_one_is_not_capped(self) -> None:
        insolvent = sheet(
            assets=section("500000", []),
            liabilities=section("800000", []),
            equity=section("-300000", []),
        )
        assert _value(compute_ratios(insolvent), "debt_ratio") == Decimal("1.600000")

    def test_a_contra_balance_reduces_the_sum_it_belongs_to(self) -> None:
        """A parenthetical figure parses to a negative and lowers its subtotal.

        Provision for doubtful debts is printed as a deduction inside current
        assets. Current assets are 400,000 - 100,000 = 300,000, so the current
        ratio is 3, not 5.
        """
        contra = sheet(
            assets=section(
                "300000",
                [
                    item("Trade receivables", "400000", "trade_receivables",
                         subsection="current", row=1),
                    item("Less: provision for doubtful debts", "-100000",
                         "other_current_assets", subsection="current", row=2),
                ],
            ),
            liabilities=section(
                "100000",
                [item("Trade payables", "100000", "trade_payables", subsection="current")],
            ),
            equity=section("200000", []),
        )
        current = compute_ratios(contra).get("current_ratio")
        assert current is not None
        assert current.numerator == Decimal("300000")
        assert current.value == Decimal("3.000000")

    def test_a_negative_line_is_not_clamped_to_zero(self) -> None:
        """The figure the document printed is the figure that is summed."""
        contra = sheet(
            assets=section(
                "300000",
                [
                    item("Trade receivables", "400000", "trade_receivables",
                         subsection="current", row=1),
                    item("Less: provision for doubtful debts", "-100000",
                         "other_current_assets", subsection="current", row=2),
                ],
            ),
            liabilities=section("100000", []),
            equity=section("200000", []),
        )
        current = compute_ratios(contra).get("current_ratio")
        assert current is not None
        assert Decimal("-100000") in [
            entry.value for entry in current.numerator_inputs
        ]


class TestPartialCoverage:
    def test_an_unmapped_current_asset_makes_liquidity_partial(self) -> None:
        partial = sheet(
            assets=section(
                "445000",
                [
                    item("Inventory", "350000", "inventory", subsection="current"),
                    item("Sundry Balances", "95000", None, subsection="current"),
                ],
            ),
            liabilities=section(
                "100000",
                [item("Trade payables", "100000", "trade_payables", subsection="current")],
            ),
            equity=section("345000", []),
        )
        current = compute_ratios(partial).get("current_ratio")
        assert current is not None
        assert current.status is RatioStatus.PARTIAL
        assert current.value == Decimal("3.500000")
        assert WARNING_UNMAPPED_INPUTS in current.warnings
        assert current.excluded_value == Decimal("95000")
        assert [entry.label for entry in current.excluded] == ["Sundry Balances"]

    def test_the_excluded_value_bounds_the_true_ratio(self) -> None:
        """Reported 3.5; with the excluded line it would be 4.45. A reader can see both."""
        partial = sheet(
            assets=section(
                "445000",
                [
                    item("Inventory", "350000", "inventory", subsection="current"),
                    item("Sundry Balances", "95000", None, subsection="current"),
                ],
            ),
            liabilities=section(
                "100000",
                [item("Trade payables", "100000", "trade_payables", subsection="current")],
            ),
            equity=section("345000", []),
        )
        current = compute_ratios(partial).get("current_ratio")
        assert current is not None
        upper = (current.numerator + current.excluded_value) / current.denominator  # type: ignore[operator]
        assert upper == Decimal("4.45")

    def test_leverage_ratios_stay_ok_when_line_items_are_unmapped(self) -> None:
        """They rest on Module 1's printed totals, not on normalization."""
        partial = sheet(
            assets=section(
                "2300000",
                [item("Assorted holdings", "2300000", None, subsection="current")],
            ),
            liabilities=section("1350000", []),
            equity=section("950000", []),
        )
        result = compute_ratios(partial)

        for name in ("debt_ratio", "equity_ratio", "debt_to_equity"):
            assert result.get(name).status is RatioStatus.OK, name  # type: ignore[union-attr]

    def test_an_excluded_line_shared_by_both_sides_is_counted_once(self) -> None:
        """The liquidity ratios share a denominator; double-counting the exclusion
        would inflate the very figure used to bound the error."""
        both = sheet(
            assets=section(
                "445000",
                [
                    item("Inventory", "350000", "inventory", subsection="current"),
                    item("Sundry Balances", "95000", None, subsection="current", row=1),
                ],
            ),
            liabilities=section(
                "200000",
                [
                    item("Trade payables", "100000", "trade_payables", subsection="current"),
                    item("Unidentified accruals", "100000", None,
                         subsection="current", row=2),
                ],
            ),
            equity=section("245000", []),
        )
        current = compute_ratios(both).get("current_ratio")
        assert current is not None
        assert current.excluded_value == Decimal("195000")
        assert len(current.excluded) == 2


class TestUnavailableReasons:
    def test_every_reason_comes_from_the_closed_set(self) -> None:
        empty = sheet(
            assets=section("0", []), liabilities=section("0", []), equity=section("0", [])
        )
        for ratio in compute_ratios(empty).ratios:
            if ratio.reason is not None:
                assert ratio.reason in REASONS, ratio.reason

    def test_every_warning_comes_from_the_closed_set(self) -> None:
        for source in (balanced_sheet(),):
            for ratio in compute_ratios(source).ratios:
                for warning in ratio.warnings:
                    assert warning in WARNINGS, warning

    def test_a_sheet_module_2_never_touched_says_not_extracted(self) -> None:
        bare = sheet(
            assets=section("2300000", []),
            liabilities=section("1350000", []),
            equity=section("950000", []),
        )
        current = compute_ratios(bare).get("current_ratio")
        assert current is not None
        assert current.reason == REASON_NOT_EXTRACTED

    def test_a_sheet_with_nothing_mapped_says_no_classified_inputs(self) -> None:
        unmapped = sheet(
            assets=section(
                "2300000", [item("Assorted holdings", "2300000", None, subsection="current")]
            ),
            liabilities=section("1350000", []),
            equity=section("950000", []),
        )
        current = compute_ratios(unmapped).get("current_ratio")
        assert current is not None
        assert current.reason == REASON_NO_CLASSIFIED_INPUTS

    def test_no_value_is_ever_invented_for_an_unavailable_ratio(self) -> None:
        empty = sheet(
            assets=section("0", []), liabilities=section("0", []), equity=section("0", [])
        )
        for ratio in compute_ratios(empty).ratios:
            if ratio.status is RatioStatus.UNAVAILABLE:
                assert ratio.value is None
                assert ratio.reason is not None


class TestPrecision:
    def test_quotients_are_quantized_to_the_declared_places(self) -> None:
        for ratio in compute_ratios(balanced_sheet()).ratios:
            if ratio.unit is RatioUnit.RATIO and ratio.value is not None:
                assert -ratio.value.as_tuple().exponent == RATIO_DECIMAL_PLACES

    def test_a_recurring_quotient_is_rounded_half_up_at_the_last_place(self) -> None:
        """2/3 = 0.666666... -> 0.666667, not 0.666666."""
        thirds = sheet(
            assets=section(
                "200000",
                [item("Cash and cash equivalents", "200000",
                      "cash_and_cash_equivalents", subsection="current")],
            ),
            liabilities=section(
                "300000",
                [item("Trade payables", "300000", "trade_payables", subsection="current")],
            ),
            equity=section("-100000", []),
        )
        assert _value(compute_ratios(thirds), "current_ratio") == Decimal("0.666667")

    def test_numerator_and_denominator_are_stored_unrounded(self) -> None:
        """So any consumer can re-derive the quotient at any precision."""
        current = compute_ratios(balanced_sheet()).get("current_ratio")
        assert current is not None
        assert current.numerator == Decimal("850000")
        assert current.denominator == Decimal("650000")

    def test_every_stored_number_is_a_decimal(self) -> None:
        for ratio in compute_ratios(balanced_sheet()).ratios:
            for number in (ratio.value, ratio.numerator, ratio.denominator):
                assert number is None or isinstance(number, Decimal)
            for entry in [*ratio.numerator_inputs, *ratio.denominator_inputs]:
                assert isinstance(entry.value, Decimal)

    def test_sums_are_exact_before_the_single_division(self) -> None:
        """No intermediate rounding: the numerator is the exact sum of its inputs."""
        current = compute_ratios(balanced_sheet()).get("current_ratio")
        assert current is not None
        assert sum(entry.value for entry in current.numerator_inputs) == current.numerator


class TestTraceability:
    def test_a_ratio_names_its_formula_and_definition(self) -> None:
        current = compute_ratios(balanced_sheet()).get("current_ratio")
        assert current is not None
        assert current.formula == "Current Assets / Current Liabilities"
        assert "cover" in current.definition

    def test_each_side_says_which_level_of_the_document_it_came_from(self) -> None:
        result = compute_ratios(balanced_sheet())

        current = result.get("current_ratio")
        assert current is not None
        assert current.numerator_basis is RatioBasis.DERIVED_SUM
        assert current.denominator_basis is RatioBasis.DERIVED_SUM

        debt = result.get("debt_ratio")
        assert debt is not None
        assert debt.numerator_basis is RatioBasis.SECTION_TOTAL
        assert debt.denominator_basis is RatioBasis.SECTION_TOTAL

    def test_every_input_walks_back_to_a_printed_label_and_a_source(self) -> None:
        current = compute_ratios(balanced_sheet()).get("current_ratio")
        assert current is not None
        for entry in current.numerator_inputs:
            assert entry.canonical_label
            assert entry.label
            assert entry.source is not None
            assert entry.source.row is not None

    def test_the_numerator_is_reconstructible_from_its_inputs(self) -> None:
        """"Where did 850,000 come from?" is answered by reading the result."""
        current = compute_ratios(balanced_sheet()).get("current_ratio")
        assert current is not None
        assert [entry.canonical_label for entry in current.numerator_inputs] == [
            "cash_and_cash_equivalents",
            "trade_receivables",
            "inventory",
            "other_current_assets",
        ]


class TestVersioningAndMetadata:
    def test_the_spec_version_is_recorded(self) -> None:
        result = compute_ratios(balanced_sheet())
        assert result.spec_version == definitions.RATIO_SPEC_VERSION

    def test_the_taxonomy_version_is_carried_through_separately(self) -> None:
        """Two independent fields, so a formula change and a vocabulary change
        can be told apart in a stored result."""
        result = compute_ratios(balanced_sheet())
        assert result.taxonomy_version == TAXONOMY_VERSION

        under_another_vocabulary = compute_ratios(
            balanced_sheet().model_copy(update={"taxonomy_version": "0.9.0"})
        )
        assert under_another_vocabulary.taxonomy_version == "0.9.0"
        assert under_another_vocabulary.spec_version == result.spec_version

    def test_a_sheet_normalized_under_another_vocabulary_is_flagged(self) -> None:
        stale = balanced_sheet()
        stale = stale.model_copy(update={"taxonomy_version": "0.9.0"})
        result = compute_ratios(stale)
        assert any("0.9.0" in warning for warning in result.warnings)

    def test_currency_is_carried_and_scale_is_recorded_not_applied(self) -> None:
        result = compute_ratios(balanced_sheet(), scale_label="in thousands")
        assert result.currency == "INR"
        assert result.scale_label == "in thousands"
        # Recorded only. The figures are exactly as printed.
        assert _value(result, "working_capital") == Decimal("200000")


class TestPurityAndDeterminism:
    def test_it_is_synchronous(self) -> None:
        assert not inspect.iscoroutinefunction(compute_ratios)

    def test_it_takes_no_dependency_parameters(self) -> None:
        """No db handle, no provider, no settings. That is what keeps it pure."""
        parameters = set(inspect.signature(compute_ratios).parameters)
        assert parameters == {"sheet", "scale_label"}

    def test_the_same_sheet_gives_the_same_result(self) -> None:
        source = balanced_sheet()
        first = compute_ratios(source)
        second = compute_ratios(source)

        assert first.model_dump(exclude={"computed_at"}) == second.model_dump(
            exclude={"computed_at"}
        )

    def test_it_does_not_mutate_the_sheet(self) -> None:
        source = balanced_sheet()
        before = copy.deepcopy(source)
        compute_ratios(source)
        assert source == before


class TestDiagnostics:
    def test_unclassified_lines_are_reported_at_the_set_level(self) -> None:
        partial = sheet(
            assets=section(
                "95000", [item("Sundry Balances", "95000", None, subsection="current")]
            ),
            liabilities=section("0", []),
            equity=section("0", []),
        )
        result = compute_ratios(partial)

        assert [entry.label for entry in result.diagnostics.unclassified] == [
            "Sundry Balances"
        ]
        assert any("could not be classified" in warning for warning in result.warnings)

    def test_a_complete_sheet_reports_clean_diagnostics(self) -> None:
        result = compute_ratios(balanced_sheet())
        assert result.diagnostics.unclassified == []
        assert result.diagnostics.duplicate_canonical_labels == {}
        assert result.warnings == []
