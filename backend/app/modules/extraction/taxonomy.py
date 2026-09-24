from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from app.core.text import matches_any, normalise
TAXONOMY_VERSION = '1.0.0'
UNKNOWN = 'unknown'

class Section(str, Enum):
    ASSETS = 'assets'
    LIABILITIES = 'liabilities'
    EQUITY = 'equity'

class Subsection(str, Enum):
    CURRENT = 'current'
    NON_CURRENT = 'non_current'

@dataclass(frozen=True)
class Category:
    label: str
    section: Section
    subsection: Subsection | None
    description: str
CATEGORIES: tuple[Category, ...] = (Category('cash_and_cash_equivalents', Section.ASSETS, Subsection.CURRENT, 'Cash in hand, bank balances and deposits readily convertible to cash.'), Category('short_term_investments', Section.ASSETS, Subsection.CURRENT, 'Investments held for the short term, including marketable securities.'), Category('trade_receivables', Section.ASSETS, Subsection.CURRENT, 'Amounts owed by customers for goods or services already delivered.'), Category('inventory', Section.ASSETS, Subsection.CURRENT, 'Goods held for sale, work in progress, and raw materials.'), Category('prepaid_expenses', Section.ASSETS, Subsection.CURRENT, 'Costs paid in advance of the period they relate to.'), Category('other_current_assets', Section.ASSETS, Subsection.CURRENT, 'A current asset the document itself presents as a residual or miscellaneous line.'), Category('property_plant_and_equipment', Section.ASSETS, Subsection.NON_CURRENT, 'Tangible long-lived assets: land, buildings, plant, machinery, vehicles, fixtures.'), Category('intangible_assets', Section.ASSETS, Subsection.NON_CURRENT, 'Non-physical long-lived assets: goodwill, patents, trademarks, software, licences.'), Category('long_term_investments', Section.ASSETS, Subsection.NON_CURRENT, 'Investments intended to be held beyond one year, including stakes in subsidiaries and associates.'), Category('other_non_current_assets', Section.ASSETS, Subsection.NON_CURRENT, 'A non-current asset the document itself presents as a residual or miscellaneous line.'), Category('trade_payables', Section.LIABILITIES, Subsection.CURRENT, 'Amounts owed to suppliers for goods or services already received.'), Category('short_term_borrowings', Section.LIABILITIES, Subsection.CURRENT, 'Debt repayable within one year: overdrafts, short-term loans, the current portion of long-term debt.'), Category('current_tax_liabilities', Section.LIABILITIES, Subsection.CURRENT, 'Taxes owed and payable within one year.'), Category('other_current_liabilities', Section.LIABILITIES, Subsection.CURRENT, 'A current liability the document itself presents as a residual or miscellaneous line, including accruals.'), Category('long_term_borrowings', Section.LIABILITIES, Subsection.NON_CURRENT, 'Debt repayable beyond one year: term loans, debentures, bonds, mortgages.'), Category('deferred_tax_liabilities', Section.LIABILITIES, Subsection.NON_CURRENT, 'Tax expected to become payable in future periods through timing differences.'), Category('provisions', Section.LIABILITIES, Subsection.NON_CURRENT, 'Liabilities of uncertain timing or amount, such as employee benefits or warranty obligations.'), Category('other_non_current_liabilities', Section.LIABILITIES, Subsection.NON_CURRENT, 'A non-current liability the document itself presents as a residual or miscellaneous line.'), Category('share_capital', Section.EQUITY, None, 'Capital subscribed by shareholders: issued and paid-up share capital, including any share premium.'), Category('retained_earnings', Section.EQUITY, None, 'Accumulated profits not distributed to shareholders; accumulated losses where negative.'), Category('reserves_and_surplus', Section.EQUITY, None, 'Reserves other than retained earnings: general reserve, revaluation reserve, capital reserve.'), Category('other_equity', Section.EQUITY, None, 'An equity component the document itself presents as a residual or miscellaneous line.'))
_BY_LABEL: dict[str, Category] = {category.label: category for category in CATEGORIES}

def labels() -> tuple[str, ...]:
    return tuple(_BY_LABEL)

def get(label: str) -> Category | None:
    return _BY_LABEL.get(label)

def labels_for(section: Section, subsection: Subsection | None=None) -> tuple[str, ...]:
    return tuple((category.label for category in CATEGORIES if category.section is section and (subsection is None or category.subsection is subsection)))

def fits(label: str, section: Section, subsection: Subsection | None) -> bool:
    category = _BY_LABEL.get(label)
    if category is None:
        return False
    if category.section is not section:
        return False
    if subsection is not None and category.subsection is not subsection:
        return False
    return True

@dataclass(frozen=True)
class SectionHeader:
    section: Section
    subsection: Subsection | None
_SUBSECTION_HEADERS: tuple[tuple[str, Section, Subsection], ...] = (('current assets', Section.ASSETS, Subsection.CURRENT), ('current liabilities', Section.LIABILITIES, Subsection.CURRENT), ('non current assets', Section.ASSETS, Subsection.NON_CURRENT), ('non current liabilities', Section.LIABILITIES, Subsection.NON_CURRENT), ('long term liabilities', Section.LIABILITIES, Subsection.NON_CURRENT), ('fixed assets', Section.ASSETS, Subsection.NON_CURRENT))
_SECTION_HEADERS: tuple[tuple[str, Section], ...] = (('assets', Section.ASSETS), ('liabilities', Section.LIABILITIES), ('equity', Section.EQUITY), ('shareholders equity', Section.EQUITY), ("shareholders' equity", Section.EQUITY), ('stockholders equity', Section.EQUITY), ('owners equity', Section.EQUITY), ('capital and reserves', Section.EQUITY), ('shareholders funds', Section.EQUITY))
_COMBINED_HEADERS: tuple[str, ...] = ('equity and liabilities', 'liabilities and equity', 'assets and liabilities')

def match_header(label: str) -> SectionHeader | None:
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
__all__ = ['CATEGORIES', 'TAXONOMY_VERSION', 'UNKNOWN', 'Category', 'Section', 'SectionHeader', 'Subsection', 'fits', 'get', 'labels', 'labels_for', 'match_header']
