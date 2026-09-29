from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.modules.insights.context import Context

_NUMBER = re.compile(
    r"(?P<open>\()? \s* (?:(?:rs|inr|usd|eur|gbp)\.?\s*)? [₹$£€]?\s* (?P<sign>-)? (?P<digits>\d[\d,]*) (?P<fraction>\.\d+)? \s* (?P<percent>%)? (?P<close>\))?",
    re.VERBOSE | re.IGNORECASE,
)

_SCALES: dict[str, Decimal] = {
    "thousand": Decimal(1000),
    "lakh": Decimal(100000),
    "lakhs": Decimal(100000),
    "million": Decimal(1000000),
    "crore": Decimal(10000000),
    "crores": Decimal(10000000),
    "billion": Decimal(1000000000),
}
_SCALE_AFTER = re.compile(r"^\s*(" + "|".join(_SCALES) + r")\b", re.IGNORECASE)
_LIST_MARKER = re.compile(r"[ \t]*\d{1,2}[.)]\s")

_CITATION_TAG = re.compile(r"\[[FCR][^\]]*\]")

_CORRUPTED_PERCENT = re.compile(r"%(?:\s*%){3,}")

_CORRUPTED_TAIL = re.compile(r"(\[(?:F|R|C)\w+\]\)?)\s*%[\s%]{10,}")

@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    verified: tuple[str, ...] = ()
    unverified: tuple[str, ...] = ()

    def correction(self) -> str:
        if self.passed or not self.unverified:
            return ""
        figures = ", ".join(self.unverified)
        return (
            f"Your previous answer stated {figures}, which does not appear "
            "anywhere in the context you were given. "
            "You may only state figures that appear verbatim in the context, "
            "or that are the direct result of a single addition or subtraction "
            "of two figures that DO appear in the context (shown as a formula). "
            "Answer again using such figures, or say that the document does not "
            "support an answer."
        )

def sanitise_answer(text: str) -> str:
    if not text:
        return text

    text = _CORRUPTED_PERCENT.sub("%", text)

    text = _CORRUPTED_TAIL.sub(r"\1", text)
    return text.strip()

def allowed_figures(context: Context) -> frozenset[Decimal]:
    return frozenset(extract_numbers(context.groundable or context.text))

def verify(
    answer: str,
    *,
    figures_used: list[str] | tuple[str, ...],
    allowed: frozenset[Decimal],
) -> VerificationResult:
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
    return VerificationResult(
        passed=not unverified,
        verified=tuple(sorted(verified)),
        unverified=tuple(sorted(unverified)),
    )

def extract_numbers(text: str) -> set[Decimal]:

    cleaned = _CITATION_TAG.sub(" ", text or "")
    found: set[Decimal] = set()
    for match in _NUMBER.finditer(cleaned):
        if _is_a_list_marker(cleaned, match):
            continue
        value = _value_of(match)
        if value is None:
            continue
        tail = cleaned[match.end():]
        scale = _SCALE_AFTER.match(tail)
        if scale is not None:
            value *= _SCALES[scale.group(1).lower()]
        found.add(value)
    return found

def _is_a_list_marker(text: str, match: re.Match[str]) -> bool:
    start = match.start("digits")
    end = match.end("digits")
    line_start = text.rfind("\n", 0, start) + 1
    marker = _LIST_MARKER.match(text, line_start)
    return marker is not None and end < marker.end()

def _value_of(match: re.Match[str]) -> Decimal | None:
    digits = match.group("digits").replace(",", "")
    if not digits:
        return None
    raw = digits + (match.group("fraction") or "")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    bracketed = match.group("open") is not None and match.group("close") is not None
    negative = match.group("sign") is not None or (
        bracketed and _is_amount(match.group("digits"), match.group("fraction"))
    )
    return -value if negative else value

def _is_amount(digits: str, fraction: str | None) -> bool:
    return "," in digits or fraction is not None or len(digits) >= 3

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

    allowed_list = list(allowed)
    for i, a in enumerate(allowed_list):
        for b in allowed_list[i:]:
            if (a + b).quantize(quantum) == value:
                return True
            diff = (a - b).quantize(quantum)
            if diff == value or -diff == value:
                return True

    return False

def _render(value: Decimal) -> str:
    normalised = value.normalize()
    if normalised == normalised.to_integral_value():
        return str(normalised.quantize(Decimal(1)))
    return str(normalised)

__all__ = [
    "VerificationResult",
    "allowed_figures",
    "extract_numbers",
    "sanitise_answer",
    "verify",
]
