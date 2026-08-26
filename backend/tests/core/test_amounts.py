"""Reading printed figures. Pure arithmetic, no document involved."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.amounts import (
    looks_like_amount,
    looks_like_year,
    parse_amount,
)


class TestParseAmount:
    @pytest.mark.parametrize(
        ("printed", "expected"),
        [
            ("150000", "150000"),
            ("150,000", "150000"),
            ("1,234.5", "1234.5"),
            ("0", "0"),
            ("0.00", "0.00"),
        ],
    )
    def test_plain_figures(self, printed: str, expected: str) -> None:
        assert parse_amount(printed) == Decimal(expected)

    def test_indian_lakh_grouping(self) -> None:
        """``12,34,567`` is how an Indian statement prints 1234567."""
        assert parse_amount("12,34,567") == Decimal("1234567")

    @pytest.mark.parametrize("printed", ["(2,300)", "( 2,300 )", "(2300)"])
    def test_parentheses_mean_negative(self, printed: str) -> None:
        """The convention a printed Balance Sheet actually uses.

        Reading ``(2,300)`` as positive flips the sign of a real figure - an
        accumulated loss would become a profit, and the sheet would stop
        balancing for a reason nobody could see.
        """
        assert parse_amount(printed) == Decimal("-2300")

    @pytest.mark.parametrize("printed", ["-2300", "2300-", "−2300", "–2300"])
    def test_a_minus_on_either_side_and_in_any_dash(self, printed: str) -> None:
        assert parse_amount(printed) == Decimal("-2300")

    @pytest.mark.parametrize(
        "printed", ["₹150,000", "$ 150,000", "INR 150,000", "Rs. 150,000", "150,000 INR"]
    )
    def test_currency_is_stripped_not_interpreted(self, printed: str) -> None:
        assert parse_amount(printed) == Decimal("150000")

    def test_a_negative_in_parentheses_with_currency(self) -> None:
        assert parse_amount("(₹2,300)") == Decimal("-2300")

    @pytest.mark.parametrize("printed", ["-", "–", "—", "nil", "NIL", "N/A"])
    def test_a_dash_means_nil(self, printed: str) -> None:
        """Accountants print a dash rather than a zero."""
        assert parse_amount(printed) == Decimal(0)

    @pytest.mark.parametrize(
        "printed",
        ["Total Assets", "", "   ", None, "abc", "12abc", "1.2.3", "31 March 2024"],
    )
    def test_things_that_are_not_figures(self, printed: str | None) -> None:
        assert parse_amount(printed) is None

    def test_the_result_is_always_decimal_never_float(self) -> None:
        """Float would drift at the cent level and break a balancing sheet."""
        value = parse_amount("1,234.56")
        assert isinstance(value, Decimal)
        assert value == Decimal("1234.56")

    def test_precision_survives_exactly(self) -> None:
        assert parse_amount("0.1") + parse_amount("0.2") == Decimal("0.3")


class TestLooksLike:
    def test_amounts_are_recognised(self) -> None:
        assert looks_like_amount("150,000") is True
        assert looks_like_amount("Total Assets") is False

    def test_a_year_is_told_apart_from_a_figure(self) -> None:
        """``2024`` parses as a number, but a column heading is not a figure."""
        assert looks_like_amount("2024") is True
        assert looks_like_year("2024") is True
        assert looks_like_year("150,000") is False
        assert looks_like_year("1899") is False
