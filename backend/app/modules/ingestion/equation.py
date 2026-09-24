from __future__ import annotations
from decimal import Decimal
from typing import Any
from app.core.money import to_decimal
from app.core.schemas import EquationCheck
DEFAULT_TOLERANCE_ABS = Decimal('1')
DEFAULT_TOLERANCE_REL = Decimal('0.005')

def effective_tolerance(total_assets: Decimal, tolerance_abs: Decimal, tolerance_rel: Decimal) -> Decimal:
    if tolerance_abs < 0 or tolerance_rel < 0:
        raise ValueError('tolerances must be non-negative')
    return max(tolerance_abs, tolerance_rel * abs(total_assets))

def check_equation(total_assets: Any, total_liabilities: Any, total_equity: Any, *, tolerance_abs: Decimal=DEFAULT_TOLERANCE_ABS, tolerance_rel: Decimal=DEFAULT_TOLERANCE_REL) -> EquationCheck:
    assets = to_decimal(total_assets)
    liabilities = to_decimal(total_liabilities)
    equity = to_decimal(total_equity)
    expected = liabilities + equity
    difference = assets - expected
    tolerance = effective_tolerance(assets, tolerance_abs, tolerance_rel)
    return EquationCheck(total_assets=assets, total_liabilities=liabilities, total_equity=equity, expected=expected, difference=difference, tolerance_applied=tolerance, balanced=abs(difference) <= tolerance)
__all__ = ['DEFAULT_TOLERANCE_ABS', 'DEFAULT_TOLERANCE_REL', 'check_equation', 'effective_tolerance']
