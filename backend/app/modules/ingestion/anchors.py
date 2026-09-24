from __future__ import annotations
from app.core.text import contains, matches_any
TITLE_PHRASES: tuple[str, ...] = ('balance sheet', 'statement of financial position')
OTHER_STATEMENT_PHRASES: tuple[str, ...] = ('statement of profit and loss', 'profit and loss account', 'income statement', 'statement of comprehensive income', 'cash flow statement', 'statement of cash flows', 'statement of changes in equity')
ASSETS_HEADERS: tuple[str, ...] = ('assets',)
LIABILITIES_HEADERS: tuple[str, ...] = ('liabilities',)
EQUITY_HEADERS: tuple[str, ...] = ('equity', 'shareholders equity', "shareholders' equity", 'stockholders equity', 'owners equity', 'capital and reserves')
COMBINED_HEADERS: tuple[str, ...] = ('equity and liabilities', 'liabilities and equity')
TOTAL_ASSETS_PHRASES: tuple[str, ...] = ('total assets', 'total of assets')
TOTAL_LIABILITIES_PHRASES: tuple[str, ...] = ('total liabilities', 'total of liabilities')
TOTAL_EQUITY_PHRASES: tuple[str, ...] = ('total equity', 'total shareholders equity', "total shareholders' equity", 'total stockholders equity', "total stockholders' equity", 'total owners equity', 'total capital and reserves', 'net worth')
COMBINED_TOTAL_PHRASES: tuple[str, ...] = ('total liabilities and shareholders equity', "total liabilities and shareholders' equity", 'total liabilities and stockholders equity', "total liabilities and stockholders' equity", 'total liabilities and equity', 'total equity and liabilities', 'total liabilities and owners equity', 'total liabilities and net worth')
SECTION_TERMS: dict[str, tuple[str, ...]] = {'assets': ASSETS_HEADERS, 'liabilities': LIABILITIES_HEADERS, 'equity': EQUITY_HEADERS + ('net worth',)}

def sections_named(label: str) -> set[str]:
    return {section for section, terms in SECTION_TERMS.items() if matches_any(label, terms) is not None}

def is_combined_total(label: str) -> bool:
    if not contains(label, 'total'):
        return False
    return len(sections_named(label)) >= 2
SCALE_PHRASES: dict[str, str] = {'in thousands': '1000', 'rs in thousands': '1000', 'amounts in thousands': '1000', 'figures in thousands': '1000', 'in 000s': '1000', 'in lakhs': '100000', 'rs in lakhs': '100000', 'in lacs': '100000', 'in millions': '1000000', 'amounts in millions': '1000000', 'in crores': '10000000', 'rs in crores': '10000000', 'in billions': '1000000000'}
CURRENCY_SYMBOLS: dict[str, str] = {'₹': 'INR', '$': 'USD', '€': 'EUR', '£': 'GBP', '¥': 'JPY'}
CURRENCY_WORDS: dict[str, str] = {'inr': 'INR', 'rupees': 'INR', 'rs': 'INR', 'usd': 'USD', 'dollars': 'USD', 'eur': 'EUR', 'euros': 'EUR', 'gbp': 'GBP', 'pounds': 'GBP', 'jpy': 'JPY', 'yen': 'JPY'}
__all__ = ['ASSETS_HEADERS', 'COMBINED_HEADERS', 'COMBINED_TOTAL_PHRASES', 'CURRENCY_SYMBOLS', 'CURRENCY_WORDS', 'EQUITY_HEADERS', 'LIABILITIES_HEADERS', 'OTHER_STATEMENT_PHRASES', 'SCALE_PHRASES', 'SECTION_TERMS', 'TITLE_PHRASES', 'TOTAL_ASSETS_PHRASES', 'TOTAL_EQUITY_PHRASES', 'TOTAL_LIABILITIES_PHRASES', 'is_combined_total', 'sections_named']
