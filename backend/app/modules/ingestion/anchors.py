"""The narrow phrase set Module 1 is allowed to know.

MODULE BOUNDARY - read this before adding anything below.

Module 1 answers two questions and no others:

1. Is this document a Balance Sheet?
2. Where are its three section totals?

So this file contains **only** the phrases needed for those: document titles,
the three section headers, and the three total lines. That is it.

**This is not a financial terminology dictionary and must never become one.**
The moment a line-item synonym appears here - "trade receivables", "sundry
debtors", "cash and bank balances" - the boundary is gone, and Module 2's
vocabulary has a competing half-copy in Module 1 that will drift out of step
with it. Full line-item extraction and all normalisation belong to
``app.modules.extraction``. When that vocabulary exists, the locator in
:mod:`app.modules.ingestion.identification` delegates to it rather than growing
its own.

If a task seems to need a line-item term here, that is the signal to stop and
raise the boundary question, not to add the term.
"""

from __future__ import annotations

import re
import unicodedata

# --------------------------------------------------------------------------
# Text normalisation - shape only, not meaning
# --------------------------------------------------------------------------

# Deliberately limited to case, whitespace and punctuation *shape*. It maps no
# financial term to any other, which is what keeps it out of Module 2's
# territory. The one word it does produce is the connector "and", written from
# the symbols "+" and "&" - that is punctuation shape, not terminology: the
# same two nouns joined the same way, spelled differently by the typesetter.
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


# --------------------------------------------------------------------------
# Document identity
# --------------------------------------------------------------------------

TITLE_PHRASES: tuple[str, ...] = (
    "balance sheet",
    "statement of financial position",
)

# Titles of the statements this project explicitly does not handle. Present so
# an Income Statement is rejected as what it is, rather than drifting through
# on a stray "total" line.
OTHER_STATEMENT_PHRASES: tuple[str, ...] = (
    "statement of profit and loss",
    "profit and loss account",
    "income statement",
    "statement of comprehensive income",
    "cash flow statement",
    "statement of cash flows",
    "statement of changes in equity",
)

# --------------------------------------------------------------------------
# Section headers
# --------------------------------------------------------------------------

ASSETS_HEADERS: tuple[str, ...] = ("assets",)
LIABILITIES_HEADERS: tuple[str, ...] = ("liabilities",)
EQUITY_HEADERS: tuple[str, ...] = (
    "equity",
    "shareholders equity",
    "shareholders' equity",
    "stockholders equity",
    "owners equity",
    "capital and reserves",
)
# Schedule III and IFRS presentations head a single combined block. It is
# evidence of a Balance Sheet, and evidence of both sections at once.
COMBINED_HEADERS: tuple[str, ...] = (
    "equity and liabilities",
    "liabilities and equity",
)

# --------------------------------------------------------------------------
# Total lines - the only figures Module 1 locates
# --------------------------------------------------------------------------

TOTAL_ASSETS_PHRASES: tuple[str, ...] = (
    "total assets",
    "total of assets",
)

TOTAL_LIABILITIES_PHRASES: tuple[str, ...] = (
    "total liabilities",
    "total of liabilities",
)

TOTAL_EQUITY_PHRASES: tuple[str, ...] = (
    "total equity",
    "total shareholders equity",
    "total shareholders' equity",
    "total stockholders equity",
    "total stockholders' equity",
    "total owners equity",
    "total capital and reserves",
    "net worth",
)

# The trap this whole file has to get right.
#
# "Total Liabilities and Shareholders' Equity" is the *balancing footer* - it
# equals Total Assets, not Total Liabilities. Reading it as the liabilities
# total inflates liabilities by the whole of equity, and the accounting
# equation then fails on a Balance Sheet that balances perfectly. Because it
# contains the literal substring "total liabilities", any matcher that does not
# rule it out first will make exactly that mistake.
COMBINED_TOTAL_PHRASES: tuple[str, ...] = (
    "total liabilities and shareholders equity",
    "total liabilities and shareholders' equity",
    "total liabilities and stockholders equity",
    "total liabilities and stockholders' equity",
    "total liabilities and equity",
    "total equity and liabilities",
    "total liabilities and owners equity",
    "total liabilities and net worth",
)


# Which words name which section. Assembled entirely from the constants above
# plus "net worth", which TOTAL_EQUITY_PHRASES already carries - so this adds
# no vocabulary to Module 1, it only indexes what is here by section.
SECTION_TERMS: dict[str, tuple[str, ...]] = {
    "assets": ASSETS_HEADERS,
    "liabilities": LIABILITIES_HEADERS,
    "equity": EQUITY_HEADERS + ("net worth",),
}


def sections_named(label: str) -> set[str]:
    """Which of the three sections this label mentions.

    ``"Total Liabilities"`` names one; ``"TOTAL LIABILITIES + EQUITY"`` names
    two. That count is what distinguishes a section total from the balancing
    footer, and it holds for phrasings nobody has thought to enumerate.
    """
    return {
        section
        for section, terms in SECTION_TERMS.items()
        if matches_any(label, terms) is not None
    }


def is_combined_total(label: str) -> bool:
    """Whether this line is the balancing footer rather than a section total.

    Checked *before* the section totals, always. See the note above
    :data:`COMBINED_TOTAL_PHRASES`.

    Decided **structurally**, not by lookup: a total line that names two or
    more of the three sections is a combined total, and therefore cannot be any
    single section's total. Matching a list of exact phrasings cannot work here
    - connectors (``+``, ``&``, ``and``), orderings and equity synonyms
    multiply faster than a list can be maintained, and because the footer
    contains the literal text "total liabilities" by construction, *every* miss
    fails in the same direction: liabilities inflated by the whole of equity.
    :data:`COMBINED_TOTAL_PHRASES` is kept as documentation of the canonical
    forms; correctness no longer depends on it being complete.

    The ``total`` gate is what keeps the bare Schedule III block heading
    ``EQUITY AND LIABILITIES`` out - it names two sections but is not a total
    line and carries no figure.
    """
    if not contains(label, "total"):
        return False
    return len(sections_named(label)) >= 2


# --------------------------------------------------------------------------
# Units and currency - recorded as metadata, never applied
# --------------------------------------------------------------------------

SCALE_PHRASES: dict[str, str] = {
    "in thousands": "1000",
    "rs in thousands": "1000",
    "amounts in thousands": "1000",
    "figures in thousands": "1000",
    "in 000s": "1000",
    "in lakhs": "100000",
    "rs in lakhs": "100000",
    "in lacs": "100000",
    "in millions": "1000000",
    "amounts in millions": "1000000",
    "in crores": "10000000",
    "rs in crores": "10000000",
    "in billions": "1000000000",
}

CURRENCY_SYMBOLS: dict[str, str] = {
    "₹": "INR",
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
}

CURRENCY_WORDS: dict[str, str] = {
    "inr": "INR",
    "rupees": "INR",
    "rs": "INR",
    "usd": "USD",
    "dollars": "USD",
    "eur": "EUR",
    "euros": "EUR",
    "gbp": "GBP",
    "pounds": "GBP",
    "jpy": "JPY",
    "yen": "JPY",
}


__all__ = [
    "ASSETS_HEADERS",
    "COMBINED_HEADERS",
    "COMBINED_TOTAL_PHRASES",
    "CURRENCY_SYMBOLS",
    "CURRENCY_WORDS",
    "EQUITY_HEADERS",
    "LIABILITIES_HEADERS",
    "OTHER_STATEMENT_PHRASES",
    "SCALE_PHRASES",
    "SECTION_TERMS",
    "TITLE_PHRASES",
    "TOTAL_ASSETS_PHRASES",
    "TOTAL_EQUITY_PHRASES",
    "TOTAL_LIABILITIES_PHRASES",
    "contains",
    "is_combined_total",
    "matches_any",
    "normalise",
    "sections_named",
]
