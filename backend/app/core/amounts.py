from __future__ import annotations
import re
from decimal import Decimal, InvalidOperation
NIL_MARKERS = frozenset({'-', '--', '–', '—', 'nil', 'n/a', 'na'})
CURRENCY_CHARACTERS = '$€£¥₹₩₪₦₱¢'
CURRENCY_CODES = re.compile('\\b(?:INR|USD|EUR|GBP|JPY|AUD|CAD|CHF|CNY|SGD|AED|Rs)\\.?(?!\\w)', re.IGNORECASE)
_WHITESPACE = re.compile('[\\s\xa0\u2007\u202f]+')
_NUMERIC = re.compile('^\\d+(?:\\.\\d+)?$')
_YEAR = re.compile('^(?:19|20)\\d{2}$')

def parse_amount(text: str | None) -> Decimal | None:
    if text is None:
        return None
    cleaned = _WHITESPACE.sub(' ', str(text)).strip()
    if not cleaned:
        return None
    if cleaned.lower() in NIL_MARKERS:
        return Decimal(0)
    negative = False
    if cleaned.startswith('(') and cleaned.endswith(')'):
        negative = True
        cleaned = cleaned[1:-1].strip()
    cleaned = CURRENCY_CODES.sub('', cleaned)
    cleaned = cleaned.strip(CURRENCY_CHARACTERS + ' ').strip()
    for marker in ('-', '−', '–'):
        if cleaned.startswith(marker):
            negative = not negative
            cleaned = cleaned[len(marker):].strip()
            break
    if cleaned.endswith('-'):
        negative = not negative
        cleaned = cleaned[:-1].strip()
    cleaned = cleaned.replace(',', '').replace(' ', '')
    if not cleaned or not _NUMERIC.match(cleaned):
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return -value if negative else value

def looks_like_amount(text: str | None) -> bool:
    return parse_amount(text) is not None

def looks_like_year(text: str | None) -> bool:
    if text is None:
        return False
    return bool(_YEAR.match(str(text).strip()))
__all__ = ['CURRENCY_CHARACTERS', 'NIL_MARKERS', 'looks_like_amount', 'looks_like_year', 'parse_amount']
