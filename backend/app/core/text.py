"""Label text shaping - shape only, never meaning.

Reduces a printed label to a comparable form so that two spellings of the same
words match. It maps no financial term to any other, which is what keeps it out
of Module 2's territory: this decides that ``SHAREHOLDERS' EQUITY`` and
``Shareholders' Equity`` are the same *string*, not that "Trade Debtors" and
"Trade Receivables" are the same *concept*.

It lives in ``core`` because both modules key on it and they must agree.
Module 1 matches anchor phrases with it; Module 2 keys its identity dictionary
and its normalization cache with it. Two implementations would mean a cache
that cannot find what the dictionary just stored.
"""

from __future__ import annotations

import re
import unicodedata

# Deliberately limited to case, whitespace and punctuation *shape*. The one
# word it produces is the connector "and", written from the symbols "+" and
# "&" - that is punctuation shape, not terminology: the same two nouns joined
# the same way, spelled differently by the typesetter.
_APOSTROPHES = {"‘": "'", "’": "'", "ʼ": "'", "`": "'"}
_DASHES = {"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-"}
_CONNECTORS = re.compile(r"[+&]")
_COLLAPSE = re.compile(r"[^a-z0-9]+")


def normalise(text: str) -> str:
    """Reduce a label to a comparable shape: lower case, single spaces.

    Punctuation differences are what actually break naive matching here.
    A PDF's Helvetica encoding renders an apostrophe as U+2019, so
    ``SHAREHOLDERS' EQUITY`` comes back as ``SHAREHOLDERS’ EQUITY`` and a
    literal string comparison fails on a document that is perfectly ordinary.

    ``+`` and ``&`` become the word ``and`` before the collapse, so that
    ``TOTAL LIABILITIES + EQUITY`` and ``Total Liabilities and Equity`` reduce
    to one string. Without this the collapse deletes the connector outright and
    the two forms stop being comparable at all. ``/`` is deliberately left to
    the collapse: in these documents it separates the parts of a date
    (``31/03/2024``) far more often than it joins two nouns.
    """
    folded = unicodedata.normalize("NFKC", text)
    for source, target in {**_APOSTROPHES, **_DASHES}.items():
        folded = folded.replace(source, target)
    folded = _CONNECTORS.sub(" and ", folded)
    return _COLLAPSE.sub(" ", folded.lower()).strip()


def contains(haystack: str, phrase: str) -> bool:
    """Whether ``phrase`` appears in ``haystack``, both normalised."""
    return f" {normalise(phrase)} " in f" {normalise(haystack)} "


def matches_any(text: str, phrases: tuple[str, ...]) -> str | None:
    """Return the first phrase found in ``text``, or ``None``.

    Longest phrase first, so ``total liabilities and equity`` is recognised as
    itself rather than as ``total liabilities``.
    """
    for phrase in sorted(phrases, key=len, reverse=True):
        if contains(text, phrase):
            return phrase
    return None


__all__ = ["contains", "matches_any", "normalise"]
