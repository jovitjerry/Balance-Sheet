from __future__ import annotations
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from app.modules.insights.context import Context
_NUMBER = re.compile("\n    (?P<open>\\()?                       # (2,300) - the accountant's minus\n    \\s*\n    (?:(?:rs|inr|usd|eur|gbp)\\.?\\s*)?   # currency code\n    [₹$£€]?\\s*           # or currency symbol\n    (?P<sign>-)?\n    (?P<digits>\\d[\\d,]*)                # 2,300,000 or 23,00,000 or 2300000\n    (?P<fraction>\\.\\d+)?\n    \\s*\n    (?P<percent>%)?\n    (?P<close>\\))?\n    ", re.VERBOSE | re.IGNORECASE)
_SCALES: dict[str, Decimal] = {'thousand': Decimal(1000), 'lakh': Decimal(100000), 'lakhs': Decimal(100000), 'million': Decimal(1000000), 'crore': Decimal(10000000), 'crores': Decimal(10000000), 'billion': Decimal(1000000000)}
_SCALE_AFTER = re.compile('^\\s*(' + '|'.join(_SCALES) + ')\\b', re.IGNORECASE)
_LIST_MARKER = re.compile('[ \\t]*\\d{1,2}[.)]\\s')

@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    verified: tuple[str, ...] = ()
    unverified: tuple[str, ...] = ()

    def correction(self) -> str:
        if self.passed or not self.unverified:
            return ''
        figures = ', '.join(self.unverified)
        return f'Your previous answer stated {figures}, which does not appear anywhere in the context you were given. Do not calculate or derive figures. Answer again using only figures that appear verbatim in the context, or say that the document does not support an answer.'

def allowed_figures(context: Context) -> frozenset[Decimal]:
    return frozenset(extract_numbers(context.groundable or context.text))

def verify(answer: str, *, figures_used: list[str] | tuple[str, ...], allowed: frozenset[Decimal]) -> VerificationResult:
    candidates: dict[Decimal, str] = {}
    for value in extract_numbers(answer):
        candidates[value] = _render(value)
    for declared in figures_used:
        for value in extract_numbers(str(declared)):
            candidates.setdefault(value, _render(value))
    verified: list[str] = []
    unverified: list[str] = []
    for value, printed in candidates.items():
        (verified if _matches(value, allowed) else unverified).append(printed)
    return VerificationResult(passed=not unverified, verified=tuple(sorted(verified)), unverified=tuple(sorted(unverified)))

def extract_numbers(text: str) -> set[Decimal]:
    found: set[Decimal] = set()
    for match in _NUMBER.finditer(text or ''):
        if _is_a_list_marker(text, match):
            continue
        value = _value_of(match)
        if value is None:
            continue
        tail = text[match.end():]
        scale = _SCALE_AFTER.match(tail)
        if scale is not None:
            value *= _SCALES[scale.group(1).lower()]
        found.add(value)
    return found

def _is_a_list_marker(text: str, match: re.Match[str]) -> bool:
    start = match.start('digits')
    end = match.end('digits')
    line_start = text.rfind('\n', 0, start) + 1
    marker = _LIST_MARKER.match(text, line_start)
    return marker is not None and end < marker.end()

def _value_of(match: re.Match[str]) -> Decimal | None:
    digits = match.group('digits').replace(',', '')
    if not digits:
        return None
    raw = digits + (match.group('fraction') or '')
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    bracketed = match.group('open') is not None and match.group('close') is not None
    negative = match.group('sign') is not None or (bracketed and _is_amount(match.group('digits'), match.group('fraction')))
    return -value if negative else value

def _is_amount(digits: str, fraction: str | None) -> bool:
    return ',' in digits or fraction is not None or len(digits) >= 3

def _matches(value: Decimal, allowed: frozenset[Decimal]) -> bool:
    if value in allowed:
        return True
    places = -value.as_tuple().exponent
    quantum = Decimal(1).scaleb(-places) if places > 0 else Decimal(1)
    for candidate in allowed:
        if candidate.quantize(quantum) == value:
            return True
        if (candidate * 100).quantize(quantum) == value:
            return True
        if places > 0 and (candidate / 100).quantize(quantum) == value:
            return True
    return False

def _render(value: Decimal) -> str:
    normalised = value.normalize()
    if normalised == normalised.to_integral_value():
        return str(normalised.quantize(Decimal(1)))
    return str(normalised)
__all__ = ['VerificationResult', 'allowed_figures', 'extract_numbers', 'verify']
