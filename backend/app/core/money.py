"""Money handling.

Every monetary value in this project is a :class:`decimal.Decimal`, never a
``float``. Binary floating point drifts at the cent level, which would make the
accounting-equation check fail on balance sheets that genuinely balance.

In MongoDB these are stored as ``Decimal128``. The conversion happens here, at
the boundary, so no module has to think about it.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext
from typing import Annotated, Any

from bson.decimal128 import Decimal128, create_decimal128_context
from pydantic import BeforeValidator

# Decimal128 is IEEE 754-2008 decimal128: 34 significant digits.
DECIMAL128_SIG_DIGITS = 34

_D128_CONTEXT = create_decimal128_context()


def to_decimal(value: Any) -> Decimal:
    """Coerce a value read from Mongo, JSON, or a parser into ``Decimal``.

    Accepts ``Decimal``, ``Decimal128``, ``int`` and ``str``. ``float`` is
    rejected outright: silently accepting one would reintroduce exactly the
    binary drift this module exists to prevent. Convert it to ``str`` at the
    call site, where the precision loss is visible.

    Every rejection raises ``ValueError``, including ones that are really type
    errors. This function backs a pydantic ``BeforeValidator``, and pydantic
    converts only ``ValueError``/``AssertionError`` into a ``ValidationError``;
    a ``TypeError`` would escape as an unhandled 500 instead of a 422.
    """
    if isinstance(value, Decimal):
        return _check_finite(value)
    if isinstance(value, Decimal128):
        return _check_finite(value.to_decimal())
    if isinstance(value, bool):  # bool is an int subclass; never a money value
        raise ValueError("bool is not a monetary value")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return _check_finite(Decimal(value.strip()))
        except InvalidOperation as exc:
            raise ValueError(f"not a valid decimal number: {value!r}") from exc
    if isinstance(value, float):
        raise ValueError(
            "float is not accepted for monetary values - use Decimal or str "
            f"(got {value!r})"
        )
    raise ValueError(f"cannot interpret {type(value).__name__} as a monetary value")


def _check_finite(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise ValueError(f"monetary value must be finite, got {value}")
    return value


def to_decimal128(value: Decimal) -> Decimal128:
    """Convert a ``Decimal`` to ``Decimal128`` for storage.

    Raises if the value cannot be represented exactly, rather than letting
    MongoDB round it silently.
    """
    value = _check_finite(value)
    digits = len(value.as_tuple().digits)
    if digits > DECIMAL128_SIG_DIGITS:
        raise ValueError(
            f"value has {digits} significant digits, exceeding Decimal128's "
            f"{DECIMAL128_SIG_DIGITS}: {value}"
        )
    with localcontext(_D128_CONTEXT):
        return Decimal128(value)


def encode_for_mongo(value: Any) -> Any:
    """Recursively convert ``Decimal`` to ``Decimal128`` in a dumped document.

    Apply to the result of ``model_dump()`` immediately before writing. JSON
    responses do NOT go through this - pydantic serializes ``Decimal`` directly.
    """
    if isinstance(value, Decimal):
        return to_decimal128(value)
    if isinstance(value, dict):
        return {key: encode_for_mongo(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode_for_mongo(item) for item in value]
    return value


def decode_from_mongo(value: Any) -> Any:
    """Inverse of :func:`encode_for_mongo`, for documents read back."""
    if isinstance(value, Decimal128):
        return value.to_decimal()
    if isinstance(value, dict):
        return {key: decode_from_mongo(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode_from_mongo(item) for item in value]
    return value


Money = Annotated[Decimal, BeforeValidator(to_decimal)]
"""A monetary amount. Accepts Decimal/Decimal128/int/str; rejects float."""


__all__ = [
    "DECIMAL128_SIG_DIGITS",
    "Money",
    "decode_from_mongo",
    "encode_for_mongo",
    "to_decimal",
    "to_decimal128",
]
