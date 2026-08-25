"""The accounting-equation validator.

    Total Assets = Total Liabilities + Shareholders' Equity

Pure and synchronous: no database, no I/O, no LLM. Financial validation is
deterministic Python and must never be delegated to a language model.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.core.money import to_decimal
from app.core.schemas import EquationCheck

# Defaults mirror app.core.config.Settings; passing explicit values is
# preferred so callers stay honest about which tolerance they applied.
DEFAULT_TOLERANCE_ABS = Decimal("1")
DEFAULT_TOLERANCE_REL = Decimal("0.005")


def effective_tolerance(
    total_assets: Decimal,
    tolerance_abs: Decimal,
    tolerance_rel: Decimal,
) -> Decimal:
    """Return the absolute threshold actually applied.

    ``max(abs, rel * |total_assets|)``. Published balance sheets are rounded -
    often to thousands - so a fixed absolute tolerance is simultaneously too
    tight for a large company and meaninglessly loose for a small one. The
    relative term scales with the statement; the absolute term is the floor
    that keeps small or zero-asset sheets sane.

    Note this multiplies rather than divides, so a zero ``total_assets`` simply
    falls back to the absolute floor - there is no division by zero to guard.
    """
    if tolerance_abs < 0 or tolerance_rel < 0:
        raise ValueError("tolerances must be non-negative")
    return max(tolerance_abs, tolerance_rel * abs(total_assets))


def check_equation(
    total_assets: Any,
    total_liabilities: Any,
    total_equity: Any,
    *,
    tolerance_abs: Decimal = DEFAULT_TOLERANCE_ABS,
    tolerance_rel: Decimal = DEFAULT_TOLERANCE_REL,
) -> EquationCheck:
    """Validate the accounting equation.

    Arguments accept anything :func:`app.core.money.to_decimal` understands -
    ``Decimal``, ``Decimal128``, ``int`` or ``str``. ``float`` is rejected.

    The signed ``difference`` is always recorded, whether or not the sheet
    balances, so a near-miss is auditable rather than a silent pass. A positive
    difference means assets exceed liabilities plus equity.

    Negative shareholders' equity (accumulated losses) is perfectly ordinary
    and balances normally - nothing here treats it as an error.
    """
    assets = to_decimal(total_assets)
    liabilities = to_decimal(total_liabilities)
    equity = to_decimal(total_equity)

    expected = liabilities + equity
    difference = assets - expected
    tolerance = effective_tolerance(assets, tolerance_abs, tolerance_rel)

    return EquationCheck(
        total_assets=assets,
        total_liabilities=liabilities,
        total_equity=equity,
        expected=expected,
        difference=difference,
        tolerance_applied=tolerance,
        balanced=abs(difference) <= tolerance,
    )


__all__ = [
    "DEFAULT_TOLERANCE_ABS",
    "DEFAULT_TOLERANCE_REL",
    "check_equation",
    "effective_tolerance",
]
