"""Tests for the accounting-equation validator.

    Total Assets = Total Liabilities + Shareholders' Equity
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.ingestion.equation import (
    check_equation,
    effective_tolerance,
)

ZERO_TOL = {"tolerance_abs": Decimal("0"), "tolerance_rel": Decimal("0")}


class TestExactBalance:
    def test_a_sheet_that_balances_exactly_is_balanced(self) -> None:
        result = check_equation("1000.00", "400.00", "600.00", **ZERO_TOL)
        assert result.balanced
        assert result.difference == Decimal("0")
        assert result.expected == Decimal("1000.00")

    def test_zero_sheet_balances(self) -> None:
        assert check_equation("0", "0", "0", **ZERO_TOL).balanced


class TestTolerance:
    def test_difference_inside_absolute_tolerance_is_balanced(self) -> None:
        # Off by 0.40, absolute floor is 1.00.
        result = check_equation(
            "1000.40", "400.00", "600.00",
            tolerance_abs=Decimal("1"), tolerance_rel=Decimal("0"),
        )
        assert result.balanced
        assert result.difference == Decimal("0.40")
        assert result.tolerance_applied == Decimal("1")

    def test_difference_outside_tolerance_is_unbalanced(self) -> None:
        result = check_equation(
            "1050.00", "400.00", "600.00",
            tolerance_abs=Decimal("1"), tolerance_rel=Decimal("0"),
        )
        assert not result.balanced
        assert result.difference == Decimal("50.00")

    def test_difference_exactly_at_tolerance_is_balanced(self) -> None:
        # Boundary is inclusive: <= tolerance, not <.
        result = check_equation(
            "1001", "400", "600",
            tolerance_abs=Decimal("1"), tolerance_rel=Decimal("0"),
        )
        assert result.balanced
        assert result.difference == Decimal("1")

    def test_rounded_to_thousands_sheet_passes_on_relative_tolerance(self) -> None:
        """The case the relative term exists for.

        A sheet reported in thousands is off by 3 units on a 10,000,000 total -
        a rounding artefact, not an error. The absolute floor of 1 would reject
        it; 0.5% of assets accepts it.
        """
        result = check_equation(
            "10000003", "6000000", "4000000",
            tolerance_abs=Decimal("1"), tolerance_rel=Decimal("0.005"),
        )
        assert result.balanced
        assert result.tolerance_applied == Decimal("50000.015")

    def test_relative_tolerance_still_rejects_a_real_error(self) -> None:
        # 8% off is not a rounding artefact.
        result = check_equation(
            "10800000", "6000000", "4000000",
            tolerance_abs=Decimal("1"), tolerance_rel=Decimal("0.005"),
        )
        assert not result.balanced

    def test_small_sheet_falls_back_to_the_absolute_floor(self) -> None:
        """0.5% of a tiny total would be uselessly strict; the floor governs."""
        assert effective_tolerance(
            Decimal("10"), Decimal("1"), Decimal("0.005")
        ) == Decimal("1")

    def test_zero_assets_does_not_divide_by_zero(self) -> None:
        """The relative term multiplies, so a zero total degenerates safely."""
        result = check_equation(
            "0", "100", "-100",
            tolerance_abs=Decimal("1"), tolerance_rel=Decimal("0.005"),
        )
        assert result.tolerance_applied == Decimal("1")
        assert result.balanced

    def test_negative_tolerance_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            check_equation("1", "1", "0", tolerance_abs=Decimal("-1"))


class TestDifferenceSign:
    def test_positive_when_assets_exceed_liabilities_plus_equity(self) -> None:
        result = check_equation("1100", "400", "600", **ZERO_TOL)
        assert result.difference == Decimal("100")

    def test_negative_when_assets_fall_short(self) -> None:
        result = check_equation("900", "400", "600", **ZERO_TOL)
        assert result.difference == Decimal("-100")

    def test_difference_is_recorded_even_when_balanced(self) -> None:
        """A near-miss must be auditable rather than a silent pass."""
        result = check_equation(
            "1000.25", "400", "600.00",
            tolerance_abs=Decimal("1"), tolerance_rel=Decimal("0"),
        )
        assert result.balanced
        assert result.difference == Decimal("0.25")


class TestNegativeEquity:
    def test_accumulated_losses_still_balance(self) -> None:
        """Negative shareholders' equity is ordinary, not an error."""
        result = check_equation("500000", "800000", "-300000", **ZERO_TOL)
        assert result.balanced
        assert result.total_equity == Decimal("-300000")

    def test_negative_equity_that_does_not_balance_is_caught(self) -> None:
        result = check_equation("500000", "800000", "-250000", **ZERO_TOL)
        assert not result.balanced
        assert result.difference == Decimal("-50000")


class TestDecimalNotFloat:
    def test_float_input_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="float is not accepted"):
            check_equation(1000.10, 400.05, 600.05)

    def test_the_case_float_would_have_failed(self) -> None:
        """Why this module refuses floats.

        0.1 + 0.2 != 0.3 in binary floating point, so a float implementation
        reports a non-zero difference on a sheet that balances perfectly. With
        Decimal and zero tolerance, it balances exactly.
        """
        assert 0.1 + 0.2 != 0.3  # the float bug, demonstrated

        result = check_equation("0.3", "0.1", "0.2", **ZERO_TOL)
        assert result.balanced
        assert result.difference == Decimal("0")

    def test_accepts_decimal_int_and_str(self) -> None:
        assert check_equation(Decimal("100"), 40, "60", **ZERO_TOL).balanced

    def test_bool_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="bool"):
            check_equation(True, 0, 1, **ZERO_TOL)

    def test_unparseable_string_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="not a valid decimal"):
            check_equation("1,000", "400", "600", **ZERO_TOL)


class TestPrecisionPreserved:
    def test_cent_level_difference_is_not_lost(self) -> None:
        result = check_equation("1000000000.01", "600000000.00", "400000000.00", **ZERO_TOL)
        assert not result.balanced
        assert result.difference == Decimal("0.01")
