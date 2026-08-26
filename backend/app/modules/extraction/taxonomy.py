"""The canonical Balance Sheet vocabulary. Module 2 owns this and nothing else does.

This is the file Module 1 is forbidden to grow a copy of. Module 1's
``anchors.py`` knows document titles, the three section names and the three
total lines; everything below - the line-item concepts a Balance Sheet is built
from - lives here.

Two properties do the real work.

**The vocabulary is closed.** It is handed to a language model as the complete
set of permitted answers, so the model chooses from it rather than inventing a
category. An open vocabulary would make "invent a plausible-sounding label" a
legal move, and a plausible-sounding label is exactly the kind of wrong answer
nobody catches.

**Every category declares where it can legally appear.** A model can return a
structurally valid label that is nonsense in context - ``trade_payables`` for a
line printed under ASSETS. The enum constraint cannot catch that; :func:`fits`
can, and does.

Sizing: deliberately small, and sized by what Module 3 will need to compute
(current and quick ratios, the debt ratios, working capital) rather than by how
much of accounting could be described. Growing it is a version bump, not an
edit - see :data:`TAXONOMY_VERSION`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.core.text import matches_any, normalise

# Bumped whenever a category is added, removed or redefined. Stored on every
# normalized line item, so a stored mapping always says which vocabulary
# produced it - and a bump invalidates the normalization cache by construction.
TAXONOMY_VERSION = "1.0.0"

# What the model returns when it will not commit. Deliberately *not* a category:
# an abstention is a different thing from a residual line, and collapsing the
# two would hide every label the system failed to understand inside a bucket
# that looks like a real answer.
UNKNOWN = "unknown"


class Section(str, Enum):
    ASSETS = "assets"
    LIABILITIES = "liabilities"
    EQUITY = "equity"


class Subsection(str, Enum):
    CURRENT = "current"
    NON_CURRENT = "non_current"


@dataclass(frozen=True)
class Category:
    """One canonical concept, and where on a Balance Sheet it may appear.

    ``description`` is what the prompt shows the model. Keeping it here rather
    than in the prompt is what stops the vocabulary and its documentation
    drifting apart as the taxonomy grows.
    """

    label: str
    section: Section
    subsection: Subsection | None
    description: str


CATEGORIES: tuple[Category, ...] = (
    # ---- Assets: current ----
    Category(
        "cash_and_cash_equivalents",
        Section.ASSETS,
        Subsection.CURRENT,
        "Cash in hand, bank balances and deposits readily convertible to cash.",
    ),
    Category(
        "short_term_investments",
        Section.ASSETS,
        Subsection.CURRENT,
        "Investments held for the short term, including marketable securities.",
    ),
    Category(
        "trade_receivables",
        Section.ASSETS,
        Subsection.CURRENT,
        "Amounts owed by customers for goods or services already delivered.",
    ),
    Category(
        "inventory",
        Section.ASSETS,
        Subsection.CURRENT,
        "Goods held for sale, work in progress, and raw materials.",
    ),
    Category(
        "prepaid_expenses",
        Section.ASSETS,
        Subsection.CURRENT,
        "Costs paid in advance of the period they relate to.",
    ),
    Category(
        "other_current_assets",
        Section.ASSETS,
        Subsection.CURRENT,
        "A current asset the document itself presents as a residual or "
        "miscellaneous line.",
    ),
    # ---- Assets: non-current ----
    Category(
        "property_plant_and_equipment",
        Section.ASSETS,
        Subsection.NON_CURRENT,
        "Tangible long-lived assets: land, buildings, plant, machinery, "
        "vehicles, fixtures.",
    ),
    Category(
        "intangible_assets",
        Section.ASSETS,
        Subsection.NON_CURRENT,
        "Non-physical long-lived assets: goodwill, patents, trademarks, "
        "software, licences.",
    ),
    Category(
        "long_term_investments",
        Section.ASSETS,
        Subsection.NON_CURRENT,
        "Investments intended to be held beyond one year, including stakes in "
        "subsidiaries and associates.",
    ),
    Category(
        "other_non_current_assets",
        Section.ASSETS,
        Subsection.NON_CURRENT,
        "A non-current asset the document itself presents as a residual or "
        "miscellaneous line.",
    ),
    # ---- Liabilities: current ----
    Category(
        "trade_payables",
        Section.LIABILITIES,
        Subsection.CURRENT,
        "Amounts owed to suppliers for goods or services already received.",
    ),
    Category(
        "short_term_borrowings",
        Section.LIABILITIES,
        Subsection.CURRENT,
        "Debt repayable within one year: overdrafts, short-term loans, the "
        "current portion of long-term debt.",
    ),
    Category(
        "current_tax_liabilities",
        Section.LIABILITIES,
        Subsection.CURRENT,
        "Taxes owed and payable within one year.",
    ),
    Category(
        "other_current_liabilities",
        Section.LIABILITIES,
        Subsection.CURRENT,
        "A current liability the document itself presents as a residual or "
        "miscellaneous line, including accruals.",
    ),
    # ---- Liabilities: non-current ----
    Category(
        "long_term_borrowings",
        Section.LIABILITIES,
        Subsection.NON_CURRENT,
        "Debt repayable beyond one year: term loans, debentures, bonds, "
        "mortgages.",
    ),
    Category(
        "deferred_tax_liabilities",
        Section.LIABILITIES,
        Subsection.NON_CURRENT,
        "Tax expected to become payable in future periods through timing "
        "differences.",
    ),
    Category(
        "provisions",
        Section.LIABILITIES,
        Subsection.NON_CURRENT,
        "Liabilities of uncertain timing or amount, such as employee benefits "
        "or warranty obligations.",
    ),
    Category(
        "other_non_current_liabilities",
        Section.LIABILITIES,
        Subsection.NON_CURRENT,
        "A non-current liability the document itself presents as a residual or "
        "miscellaneous line.",
    ),
    # ---- Equity ----
    Category(
        "share_capital",
        Section.EQUITY,
        None,
        "Capital subscribed by shareholders: issued and paid-up share capital, "
        "including any share premium.",
    ),
    Category(
        "retained_earnings",
        Section.EQUITY,
        None,
        "Accumulated profits not distributed to shareholders; accumulated "
        "losses where negative.",
    ),
    Category(
        "reserves_and_surplus",
        Section.EQUITY,
        None,
        "Reserves other than retained earnings: general reserve, revaluation "
        "reserve, capital reserve.",
    ),
    Category(
        "other_equity",
        Section.EQUITY,
        None,
        "An equity component the document itself presents as a residual or "
        "miscellaneous line.",
    ),
)

_BY_LABEL: dict[str, Category] = {category.label: category for category in CATEGORIES}


def labels() -> tuple[str, ...]:
    """Every canonical label, in taxonomy order. The closed set."""
    return tuple(_BY_LABEL)


def get(label: str) -> Category | None:
    """The category for a canonical label, or ``None`` if there is no such label."""
    return _BY_LABEL.get(label)


def labels_for(section: Section, subsection: Subsection | None = None) -> tuple[str, ...]:
    """The labels legal in one part of the sheet.

    With no subsection given, every label in the section is returned - which is
    the right set for a document that prints no current/non-current split.
    """
    return tuple(
        category.label
        for category in CATEGORIES
        if category.section is section
        and (subsection is None or category.subsection is subsection)
    )


def fits(label: str, section: Section, subsection: Subsection | None) -> bool:
    """Whether ``label`` may legally describe a line in this part of the sheet.

    The check a constrained enum cannot make. An enum guarantees the model
    returns *a* label; only this says whether the label makes sense where the
    line was printed. ``trade_payables`` under ASSETS is structurally valid and
    factually wrong, and this is what catches it.

    A line whose subsection is unknown - ordinary on sheets with no
    current/non-current headings - is checked on its section alone rather than
    refused outright.
    """
    category = _BY_LABEL.get(label)
    if category is None:
        return False
    if category.section is not section:
        return False
    if subsection is not None and category.subsection is not subsection:
        return False
    return True


# --------------------------------------------------------------------------
# Headings - the running context a line item inherits
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SectionHeader:
    """A heading, and the context it opens for the lines beneath it."""

    section: Section
    subsection: Subsection | None


# Ordered longest-intent first: "Current Assets" must be recognised as a
# subsection heading rather than as the bare "Assets" section heading.
_SUBSECTION_HEADERS: tuple[tuple[str, Section, Subsection], ...] = (
    ("current assets", Section.ASSETS, Subsection.CURRENT),
    ("current liabilities", Section.LIABILITIES, Subsection.CURRENT),
    ("non current assets", Section.ASSETS, Subsection.NON_CURRENT),
    ("non current liabilities", Section.LIABILITIES, Subsection.NON_CURRENT),
    ("long term liabilities", Section.LIABILITIES, Subsection.NON_CURRENT),
    ("fixed assets", Section.ASSETS, Subsection.NON_CURRENT),
)

_SECTION_HEADERS: tuple[tuple[str, Section], ...] = (
    ("assets", Section.ASSETS),
    ("liabilities", Section.LIABILITIES),
    ("equity", Section.EQUITY),
    ("shareholders equity", Section.EQUITY),
    ("shareholders' equity", Section.EQUITY),
    ("stockholders equity", Section.EQUITY),
    ("owners equity", Section.EQUITY),
    ("capital and reserves", Section.EQUITY),
    ("shareholders funds", Section.EQUITY),
)

# Headings that announce two sections at once. They cannot set a context: the
# specific headings printed underneath do that. Committing to either one here
# would file every equity line beneath it as a liability.
_COMBINED_HEADERS: tuple[str, ...] = (
    "equity and liabilities",
    "liabilities and equity",
    "assets and liabilities",
)


def match_header(label: str) -> SectionHeader | None:
    """Recognise a heading, not a line that merely mentions a section.

    ``ASSETS`` on its own line is a heading; ``Total assets`` and ``Assets
    pledged as security`` are not. So the whole label has to *be* the heading
    rather than contain it - otherwise every line naming a section would reset
    the context underneath it.
    """
    normalised = normalise(label)
    if not normalised:
        return None

    if matches_any(normalised, _COMBINED_HEADERS) is not None:
        return None

    for phrase, section, subsection in _SUBSECTION_HEADERS:
        if normalised == normalise(phrase):
            return SectionHeader(section=section, subsection=subsection)

    for phrase, section in _SECTION_HEADERS:
        if normalised == normalise(phrase):
            return SectionHeader(section=section, subsection=None)

    return None


__all__ = [
    "CATEGORIES",
    "TAXONOMY_VERSION",
    "UNKNOWN",
    "Category",
    "Section",
    "SectionHeader",
    "Subsection",
    "fits",
    "get",
    "labels",
    "labels_for",
    "match_header",
]
