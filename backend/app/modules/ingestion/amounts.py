"""Reading a printed figure as a number.

This is a *value* parse, not terminology normalisation: it turns the characters
``"(2,300)"`` into ``Decimal("-2300")`` and knows nothing about what the line
was called. The terminology vocabulary belongs to Module 2; this does not
touch it.

Module 1 needs this because the accounting-equation check is arithmetic, and
arithmetic needs numbers. The printed string is preserved separately and is
never replaced by the parsed value.

Results are always :class:`~decimal.Decimal`. ``float`` never appears - binary
drift at the cent level would fail Balance Sheets that genuinely balance.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# A dash in a figure column means nil. Accountants write it rather than "0".
NIL_MARKERS = frozenset({"-", "--", "–", "—", "nil", "n/a", "na"})

# Symbols and codes that may sit against a figure. Stripped, not interpreted -
# which currency it is gets recorded as metadata elsewhere.
CURRENCY_CHARACTERS = "$€£¥₹₩₪₦₱¢"
# The optional trailing dot has to sit inside the pattern rather than rely on a
# word boundary after it: in "Rs. 150,000" the character after the dot is a
# space, and \b needs a word character on one side, so \b would never match
# there. The negative lookahead does the job the boundary was meant to do -
# it keeps "Rs" from being stripped out of the middle of a real word.
CURRENCY_CODES = re.compile(
    r"\b(?:INR|USD|EUR|GBP|JPY|AUD|CAD|CHF|CNY|SGD|AED|Rs)\.?(?!\w)",
    re.IGNORECASE,
)

_WHITESPACE = re.compile(r"[\s   ]+")
# Accepts both Western (1,234,567) and Indian (12,34,567) grouping: the commas
# are simply removed, so irregular grouping needs no special case.
_NUMERIC = re.compile(r"^\d+(?:\.\d+)?$")
_YEAR = re.compile(r"^(?:19|20)\d{2}$")


def parse_amount(text: str | None) -> Decimal | None:
    """Read a printed figure as a ``Decimal``, or ``None`` if it is not one.

    Handles the conventions a Balance Sheet actually uses: thousands
    separators in either Western or Indian grouping, a currency symbol or code
    against the figure, a trailing or leading minus, a dash for nil, and
    parentheses for negative - ``(2,300)`` is how a printed statement writes
    minus two thousand three hundred, and reading it as positive would flip the
    sign of a real figure.
    """
    if text is None:
        return None

    cleaned = _WHITESPACE.sub(" ", str(text)).strip()
    if not cleaned:
        return None

    if cleaned.lower() in NIL_MARKERS:
        return Decimal(0)

    negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        negative = True
        cleaned = cleaned[1:-1].strip()

    cleaned = CURRENCY_CODES.sub("", cleaned)
    cleaned = cleaned.strip(CURRENCY_CHARACTERS + " ").strip()

    # A minus can be printed on either side, and may be a typographic dash.
    for marker in ("-", "−", "–"):
        if cleaned.startswith(marker):
            negative = not negative
            cleaned = cleaned[len(marker) :].strip()
            break
    if cleaned.endswith("-"):
        negative = not negative
        cleaned = cleaned[:-1].strip()

    cleaned = cleaned.replace(",", "").replace(" ", "")
    if not cleaned or not _NUMERIC.match(cleaned):
        return None

    try:
        value = Decimal(cleaned)
    except InvalidOperation:  # pragma: no cover - guarded by _NUMERIC
        return None
    return -value if negative else value


def looks_like_amount(text: str | None) -> bool:
    """Whether this cell reads as a figure at all."""
    return parse_amount(text) is not None


def looks_like_year(text: str | None) -> bool:
    """Whether this cell is a bare four-digit year.

    Kept distinct from :func:`looks_like_amount` because ``2024`` satisfies
    both, and a column heading must not be mistaken for a figure.
    """
    if text is None:
        return False
    return bool(_YEAR.match(str(text).strip()))


__all__ = [
    "CURRENCY_CHARACTERS",
    "NIL_MARKERS",
    "looks_like_amount",
    "looks_like_year",
    "parse_amount",
]
