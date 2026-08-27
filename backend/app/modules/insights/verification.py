"""Checking that every figure in an answer is one the model was actually shown.

This is the module that earns the right to ship a local model. On this
project's own Q&A benchmark, three of four candidates made arithmetic errors on
a Balance Sheet containing fifteen numbers - one summing current assets as
550,000 against a true 850,000 and concluding the company could not pay its
short-term bills, which is the opposite of the truth, stated fluently and
citing plausible-looking figures. Prompting alone did not prevent that, and a
reader has no way to catch it.

So the rule is mechanical: **the set of figures an answer may contain is the
set of figures placed in its context.** Module 3 computed them; the model may
repeat them and explain them; it may not produce a new one. An unmatched figure
means the model calculated or invented, and either way the answer is not
shippable.

**Tolerance is a design requirement, not a weakness.** A guard that fires on
"about 1.3" or "58.7%" refuses good answers, and a guard that refuses good
answers gets switched off. So restatement is matched generously - rounding,
percentages, scale words, either digit grouping - while an invented figure
still has nowhere to hide, because it matches nothing at any tolerance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.modules.insights.context import Context

# A number as it appears in prose: optional sign or opening parenthesis, an
# optional currency symbol or code, digits with either grouping convention, an
# optional fraction, and an optional percent or closing parenthesis.
_NUMBER = re.compile(
    r"""
    (?P<open>\()?                       # (2,300) - the accountant's minus
    \s*
    (?:(?:rs|inr|usd|eur|gbp)\.?\s*)?   # currency code
    [₹$£€]?\s*           # or currency symbol
    (?P<sign>-)?
    (?P<digits>\d[\d,]*)                # 2,300,000 or 23,00,000 or 2300000
    (?P<fraction>\.\d+)?
    \s*
    (?P<percent>%)?
    (?P<close>\))?
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Written scale, so "2.3 million" is recognised as a restatement of 2,300,000
# rather than as an invented 2.3. Indian scales included: these documents are
# printed in them.
_SCALES: dict[str, Decimal] = {
    "thousand": Decimal(1_000),
    "lakh": Decimal(100_000),
    "lakhs": Decimal(100_000),
    "million": Decimal(1_000_000),
    "crore": Decimal(10_000_000),
    "crores": Decimal(10_000_000),
    "billion": Decimal(1_000_000_000),
}
_SCALE_AFTER = re.compile(
    r"^\s*(" + "|".join(_SCALES) + r")\b", re.IGNORECASE
)


@dataclass(frozen=True)
class VerificationResult:
    """What survived the check, and what did not."""

    passed: bool
    verified: tuple[str, ...] = ()
    unverified: tuple[str, ...] = ()

    def correction(self) -> str:
        """An instruction for the retry, naming what was wrong.

        Empty when nothing was wrong. A retry that does not say what failed is
        just a second roll of the dice, and would as often produce a different
        wrong number as a right one.
        """
        if self.passed or not self.unverified:
            return ""
        figures = ", ".join(self.unverified)
        return (
            f"Your previous answer stated {figures}, which does not appear "
            "anywhere in the context you were given. Do not calculate or "
            "derive figures. Answer again using only figures that appear "
            "verbatim in the context, or say that the document does not "
            "support an answer."
        )


def allowed_figures(context: Context) -> frozenset[Decimal]:
    """Every number the model can legitimately repeat.

    Read from :attr:`~app.modules.insights.context.Context.groundable` - the
    fact, ratio and extract blocks - rather than from the whole rendered
    prompt. The breadth within those blocks is deliberate: page numbers, a
    ratio's numerator and denominator, a year quoted inside a policy note and
    the figures printed in an extract are all things a good answer may mention,
    and narrowing to the fact values alone would manufacture false refusals.

    What it excludes is just as deliberate. **Conversation history is not
    evidence.** A figure appearing only in an earlier answer was not retrieved
    this turn and may be one the model got wrong last turn; admitting it would
    let a single mistake launder itself into fact by being repeated, and every
    following answer would inherit it.
    """
    return frozenset(extract_numbers(context.groundable or context.text))


def verify(
    answer: str, *, figures_used: list[str] | tuple[str, ...], allowed: frozenset[Decimal]
) -> VerificationResult:
    """Check an answer's figures against the ones it was shown.

    Both the prose and the model's own ``figures_used`` declaration are
    checked. The declaration is not trusted as a complete list - a model that
    miscalculates may also under-report - so the prose is scanned regardless.
    """
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
    """Every numeric value in a span of prose, normalised to ``Decimal``.

    Handles both digit groupings, currency symbols and codes, the
    parenthesised negative, and a following scale word.
    """
    found: set[Decimal] = set()
    for match in _NUMBER.finditer(text or ""):
        value = _value_of(match)
        if value is None:
            continue

        tail = text[match.end() :]
        scale = _SCALE_AFTER.match(tail)
        if scale is not None:
            value *= _SCALES[scale.group(1).lower()]

        found.add(value)
    return found


def _value_of(match: re.Match[str]) -> Decimal | None:
    digits = match.group("digits").replace(",", "")
    if not digits:
        return None
    raw = digits + (match.group("fraction") or "")
    try:
        value = Decimal(raw)
    except InvalidOperation:  # pragma: no cover - the pattern only matches digits
        return None

    bracketed = match.group("open") is not None and match.group("close") is not None
    negative = match.group("sign") is not None or (
        bracketed and _is_amount(match.group("digits"), match.group("fraction"))
    )
    return -value if negative else value


def _is_amount(digits: str, fraction: str | None) -> bool:
    """Whether a parenthesised number is a figure rather than a list marker.

    ``(2,300)`` is the accountant's minus and must stay negative. ``(1)`` and
    ``(2)`` in "because: (1) ... and (2) ..." are enumeration, and reading them
    as -1 and -2 marks a perfectly grounded answer as ungrounded - which costs a
    regeneration and can end in refusing a good answer, penalising a model for
    how it formats prose.

    The two are told apart by shape: a monetary amount on these documents
    carries a thousands separator, a decimal part, or at least three digits. A
    bare one- or two-digit number in brackets is a marker or a note reference.

    Getting the threshold slightly wrong is safe in a way the original bug was
    not. Context and answer go through this same function, so a consistently
    mis-parsed ``(99)`` still matches itself on both sides. The list-marker case
    was asymmetric - the answer invented a -1 that no context could contain.
    """
    return "," in digits or fraction is not None or len(digits) >= 3


def _matches(value: Decimal, allowed: frozenset[Decimal]) -> bool:
    """Whether ``value`` is a fair restatement of something in ``allowed``.

    Four ways, each a form a careful writer would actually use:

    the figure itself; the figure rounded to however many decimals the answer
    printed ("about 1.3" for 1.307692); the figure as a percentage ("58.7%" for
    0.586957); and a percentage written back as a proportion.

    Rounding is compared at the answer's own precision, so a *less* precise
    restatement passes while a different number never does - 550,000 rounds to
    550,000 at every precision, and matches nothing.
    """
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
    """How a figure is named in the verification record.

    Normalised so ``2,300,000`` and ``2300000`` report identically - the record
    is about which *number* was unsupported, not how it was typed.
    """
    normalised = value.normalize()
    # Decimal.normalize turns 350000 into 3.5E+5, which is unreadable in a
    # report; expand it back for anything with no fractional part.
    if normalised == normalised.to_integral_value():
        return str(normalised.quantize(Decimal(1)))
    return str(normalised)


__all__ = [
    "VerificationResult",
    "allowed_figures",
    "extract_numbers",
    "verify",
]
