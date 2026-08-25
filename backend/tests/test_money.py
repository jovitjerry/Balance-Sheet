"""Tests for Decimal handling and the MongoDB Decimal128 boundary."""

from __future__ import annotations

from decimal import Decimal

import pytest
from bson.decimal128 import Decimal128
from pydantic import ValidationError

from app.core.money import (
    DECIMAL128_SIG_DIGITS,
    decode_from_mongo,
    encode_for_mongo,
    to_decimal,
    to_decimal128,
)
from app.core.schemas import (
    BalanceSheetSection,
    DocumentStatus,
    EquationCheck,
    ExtractedBalanceSheet,
    LineItem,
    SourceFile,
    StorageRef,
)
from app.core.schemas import BalanceSheetDocument


class TestToDecimal:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (Decimal("1.23"), Decimal("1.23")),
            (Decimal128("4.56"), Decimal("4.56")),
            (7, Decimal("7")),
            ("  8.90  ", Decimal("8.90")),
            ("-1200", Decimal("-1200")),
        ],
    )
    def test_accepted_inputs(self, value: object, expected: Decimal) -> None:
        assert to_decimal(value) == expected

    def test_float_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="float is not accepted"):
            to_decimal(1.23)

    def test_bool_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="bool"):
            to_decimal(True)

    def test_rejections_are_valueerror_so_pydantic_returns_422(self) -> None:
        """A TypeError here would escape pydantic as an unhandled 500."""
        with pytest.raises(ValidationError):
            BalanceSheetSection(total=1.23)

    @pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
    def test_non_finite_is_rejected(self, value: str) -> None:
        with pytest.raises(ValueError, match="finite"):
            to_decimal(value)

    def test_garbage_string_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="not a valid decimal"):
            to_decimal("1,000")


class TestDecimal128Boundary:
    def test_round_trip_preserves_the_value_and_its_scale(self) -> None:
        original = Decimal("1234567.89")
        assert to_decimal128(original).to_decimal() == original

    def test_cent_precision_survives(self) -> None:
        original = Decimal("10000000000.01")
        assert to_decimal(to_decimal128(original)) == original

    def test_too_many_significant_digits_is_refused_not_rounded(self) -> None:
        too_precise = Decimal("1" * (DECIMAL128_SIG_DIGITS + 1))
        with pytest.raises(ValueError, match="significant digits"):
            to_decimal128(too_precise)


class TestRecursiveEncoding:
    def test_nested_decimals_are_encoded(self) -> None:
        encoded = encode_for_mongo(
            {"a": Decimal("1.5"), "b": [{"c": Decimal("2.5")}], "d": "left alone"}
        )
        assert isinstance(encoded["a"], Decimal128)
        assert isinstance(encoded["b"][0]["c"], Decimal128)
        assert encoded["d"] == "left alone"

    def test_decode_is_the_inverse(self) -> None:
        original = {"a": Decimal("1.5"), "b": [{"c": Decimal("2.5")}]}
        assert decode_from_mongo(encode_for_mongo(original)) == original


def _document() -> BalanceSheetDocument:
    section = lambda total: BalanceSheetSection(  # noqa: E731 - terse test helper
        total=total, line_items=[LineItem(label="Cash", value=total)]
    )
    return BalanceSheetDocument(
        status=DocumentStatus.VALIDATED,
        source=SourceFile(
            filename="sheet.pdf",
            content_type="application/pdf",
            size_bytes=10,
            sha256="a" * 64,
            ref=StorageRef(backend="local", key="aa/aa/x.pdf", size_bytes=10, content_type="application/pdf"),
        ),
        extracted=ExtractedBalanceSheet(
            assets=section(Decimal("1000.55")),
            liabilities=section(Decimal("400.30")),
            equity=section(Decimal("600.25")),
        ),
        equation_check=EquationCheck(
            total_assets=Decimal("1000.55"),
            total_liabilities=Decimal("400.30"),
            total_equity=Decimal("600.25"),
            expected=Decimal("1000.55"),
            difference=Decimal("0"),
            tolerance_applied=Decimal("1"),
            balanced=True,
        ),
    )


class TestDocumentRoundTrip:
    def test_money_is_stored_as_decimal128(self) -> None:
        stored = _document().to_mongo()
        assert isinstance(stored["extracted"]["assets"]["total"], Decimal128)
        assert isinstance(stored["equation_check"]["difference"], Decimal128)

    def test_round_trip_preserves_every_amount(self) -> None:
        original = _document()
        restored = BalanceSheetDocument.from_mongo(original.to_mongo())
        assert restored.extracted is not None and original.extracted is not None
        assert restored.extracted.assets.total == original.extracted.assets.total
        assert restored.equation_check == original.equation_check

    def test_unset_id_is_not_written(self) -> None:
        assert "_id" not in _document().to_mongo()

    def test_a_float_amount_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            BalanceSheetSection(total=1000.55)
