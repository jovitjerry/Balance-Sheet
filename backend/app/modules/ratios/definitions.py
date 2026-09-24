from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from app.core.schemas import RatioBasis, RatioUnit
from app.modules.extraction.taxonomy import Section, Subsection
RATIO_SPEC_VERSION = '1.0.0'

class InputKind(str, Enum):
    SECTION_TOTAL = 'section_total'
    DERIVED_SUM = 'derived_sum'
    COMPOSITE = 'composite'
_BASIS: dict[InputKind, RatioBasis] = {InputKind.SECTION_TOTAL: RatioBasis.SECTION_TOTAL, InputKind.DERIVED_SUM: RatioBasis.DERIVED_SUM, InputKind.COMPOSITE: RatioBasis.COMPOSITE}

@dataclass(frozen=True)
class InputSpec:
    name: str
    kind: InputKind
    section: Section | None = None
    subsection: Subsection | None = None
    include: tuple[str, ...] = ()
    base: InputSpec | None = None
    subtract: tuple[str, ...] = ()

    @property
    def basis(self) -> RatioBasis:
        return _BASIS[self.kind]
TOTAL_ASSETS = InputSpec('Total Assets', InputKind.SECTION_TOTAL, section=Section.ASSETS)
TOTAL_LIABILITIES = InputSpec('Total Liabilities', InputKind.SECTION_TOTAL, section=Section.LIABILITIES)
TOTAL_EQUITY = InputSpec('Total Equity', InputKind.SECTION_TOTAL, section=Section.EQUITY)
CURRENT_ASSETS = InputSpec('Current Assets', InputKind.DERIVED_SUM, section=Section.ASSETS, subsection=Subsection.CURRENT)
CURRENT_LIABILITIES = InputSpec('Current Liabilities', InputKind.DERIVED_SUM, section=Section.LIABILITIES, subsection=Subsection.CURRENT)
QUICK_ASSETS = InputSpec('Quick Assets', InputKind.COMPOSITE, base=CURRENT_ASSETS, subtract=('inventory', 'prepaid_expenses'))
CASH_ASSETS = InputSpec('Cash and Equivalents', InputKind.DERIVED_SUM, section=Section.ASSETS, subsection=Subsection.CURRENT, include=('cash_and_cash_equivalents', 'short_term_investments'))

class Operation(str, Enum):
    DIVIDE = 'divide'
    SUBTRACT = 'subtract'

@dataclass(frozen=True)
class RatioDefinition:
    name: str
    formula: str
    definition: str
    limitations: str
    unit: RatioUnit
    left: InputSpec
    right: InputSpec
    operation: Operation = Operation.DIVIDE
_SINGLE_PERIOD_CAVEAT = 'Computed from a single reporting period, so it carries no trend and no industry benchmark; a value is only meaningful beside context this system does not hold.'
DEFINITIONS: tuple[RatioDefinition, ...] = (RatioDefinition(name='current_ratio', formula='Current Assets / Current Liabilities', definition='Whether the assets expected to become cash within a year cover the obligations falling due within the same year. A value below 1 means short-term obligations exceed short-term resources.', limitations='Treats every current asset as equally liquid, which inventory and prepaid expenses are not - that is what the quick ratio corrects. Both sides are summed from classified line items rather than read from a printed subtotal, so an unclassified line understates it. ' + _SINGLE_PERIOD_CAVEAT, unit=RatioUnit.RATIO, left=CURRENT_ASSETS, right=CURRENT_LIABILITIES), RatioDefinition(name='quick_ratio', formula='(Current Assets - Inventory - Prepaid Expenses) / Current Liabilities', definition="The acid test: short-term cover counting only assets that can be realised without first selling stock. This is the SUBTRACTIVE definition, chosen so that it shares the current ratio's numerator basis and the two can be read side by side. The additive form - cash plus short-term investments plus receivables, over current liabilities - is NOT used here: with a closed six-category current-asset vocabulary it silently drops anything outside the whitelist.", limitations="Because it subtracts rather than whitelists, a residual line the document presents as 'other current assets' is counted as quick, which flatters liquidity. The inputs list shows exactly what was included. " + _SINGLE_PERIOD_CAVEAT, unit=RatioUnit.RATIO, left=QUICK_ASSETS, right=CURRENT_LIABILITIES), RatioDefinition(name='cash_ratio', formula='(Cash and Cash Equivalents + Short-term Investments) / Current Liabilities', definition='The strictest liquidity measure: what could be paid immediately, without collecting a receivable or selling anything. Marketable securities are included, the common presentation; a strict cash-only variant is not used, because it under-reports every sheet that splits deposits out from cash in hand.', limitations='Deliberately severe - healthy companies routinely run well below 1, because holding enough cash to retire all current liabilities at once is poor capital use rather than prudence. Unavailable, not zero, when neither cash nor short-term investments could be identified. ' + _SINGLE_PERIOD_CAVEAT, unit=RatioUnit.RATIO, left=CASH_ASSETS, right=CURRENT_LIABILITIES), RatioDefinition(name='debt_to_equity', formula='Total Liabilities / Total Equity', definition='How much of the business is financed by creditors for each unit financed by shareholders. Uses TOTAL LIABILITIES, not borrowings alone: the borrowings-only variant needs a debt/non-debt split that the canonical vocabulary does not draw, and guessing at one would put an invented boundary inside a headline ratio.', limitations='Uninterpretable on its usual scale when equity is negative - the result goes negative and a more insolvent company reports a number closer to zero. The negative_denominator warning marks that case; the value is never clamped, because hiding insolvency is the worst thing this system could do. ' + _SINGLE_PERIOD_CAVEAT, unit=RatioUnit.RATIO, left=TOTAL_LIABILITIES, right=TOTAL_EQUITY), RatioDefinition(name='debt_ratio', formula='Total Liabilities / Total Assets', definition='The share of the asset base funded by obligations of any kind. Uses TOTAL LIABILITIES rather than borrowings alone, for the same reason as debt-to-equity: the canonical vocabulary draws no debt/non-debt boundary, and inventing one would put a guess inside a headline ratio.', limitations='Says nothing about when the debt falls due: a sheet financed entirely by twenty-year bonds and one financed entirely by overdrafts report the same figure. Read it beside the current ratio. ' + _SINGLE_PERIOD_CAVEAT, unit=RatioUnit.RATIO, left=TOTAL_LIABILITIES, right=TOTAL_ASSETS), RatioDefinition(name='equity_ratio', formula='Total Equity / Total Assets', definition='The share of the asset base funded by shareholders. The complement of the debt ratio on a sheet that balances; both are reported because both are quoted, and their sum is a useful check.', limitations='Adds no information beyond the debt ratio when the accounting equation holds. Its value is as a cross-check: if the two do not sum to 1, the section totals disagree with each other. ' + _SINGLE_PERIOD_CAVEAT, unit=RatioUnit.RATIO, left=TOTAL_EQUITY, right=TOTAL_ASSETS), RatioDefinition(name='working_capital', formula='Current Assets - Current Liabilities', definition='The absolute cushion between short-term resources and short-term obligations. A money amount rather than a ratio, so it shows scale where the current ratio shows only proportion.', limitations="Being absolute, it cannot be compared between companies of different sizes - that is the current ratio's job. It carries the sheet's printed scale, which this system records and never applies: a sheet printed 'in thousands' yields a figure in thousands. " + _SINGLE_PERIOD_CAVEAT, unit=RatioUnit.CURRENCY, left=CURRENT_ASSETS, right=CURRENT_LIABILITIES, operation=Operation.SUBTRACT))
_BY_NAME: dict[str, RatioDefinition] = {definition.name: definition for definition in DEFINITIONS}

def names() -> tuple[str, ...]:
    return tuple(_BY_NAME)

def get(name: str) -> RatioDefinition | None:
    return _BY_NAME.get(name)
__all__ = ['DEFINITIONS', 'RATIO_SPEC_VERSION', 'CASH_ASSETS', 'CURRENT_ASSETS', 'CURRENT_LIABILITIES', 'InputKind', 'InputSpec', 'Operation', 'QUICK_ASSETS', 'RatioDefinition', 'TOTAL_ASSETS', 'TOTAL_EQUITY', 'TOTAL_LIABILITIES', 'get', 'names']
