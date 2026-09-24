from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext
from typing import Annotated, Any
from bson.decimal128 import Decimal128, create_decimal128_context
from pydantic import BeforeValidator
DECIMAL128_SIG_DIGITS = 34
_D128_CONTEXT = create_decimal128_context()

def to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return _check_finite(value)
    if isinstance(value, Decimal128):
        return _check_finite(value.to_decimal())
    if isinstance(value, bool):
        raise ValueError('bool is not a monetary value')
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return _check_finite(Decimal(value.strip()))
        except InvalidOperation as exc:
            raise ValueError(f'not a valid decimal number: {value!r}') from exc
    if isinstance(value, float):
        raise ValueError(f'float is not accepted for monetary values - use Decimal or str (got {value!r})')
    raise ValueError(f'cannot interpret {type(value).__name__} as a monetary value')

def _check_finite(value: Decimal) -> Decimal:
    if not value.is_finite():
        raise ValueError(f'monetary value must be finite, got {value}')
    return value

def to_decimal128(value: Decimal) -> Decimal128:
    value = _check_finite(value)
    digits = len(value.as_tuple().digits)
    if digits > DECIMAL128_SIG_DIGITS:
        raise ValueError(f"value has {digits} significant digits, exceeding Decimal128's {DECIMAL128_SIG_DIGITS}: {value}")
    with localcontext(_D128_CONTEXT):
        return Decimal128(value)

def encode_for_mongo(value: Any) -> Any:
    if isinstance(value, Decimal):
        return to_decimal128(value)
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: encode_for_mongo(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode_for_mongo(item) for item in value]
    return value

def decode_from_mongo(value: Any) -> Any:
    if isinstance(value, Decimal128):
        return value.to_decimal()
    if isinstance(value, dict):
        return {key: decode_from_mongo(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode_from_mongo(item) for item in value]
    return value
Money = Annotated[Decimal, BeforeValidator(to_decimal)]
'A monetary amount. Accepts Decimal/Decimal128/int/str; rejects float.'
__all__ = ['DECIMAL128_SIG_DIGITS', 'Money', 'decode_from_mongo', 'encode_for_mongo', 'to_decimal', 'to_decimal128']
