# Financial ratios - definitions and assumptions

**Generated from `app/modules/ratios/definitions.py`. Do not edit by hand** - run `python -m scripts.generate_ratio_docs` instead. Generated rather than written so that the formula a report quotes and the formula the code applies cannot drift apart.

Ratio specification version: `1.0.0` · canonical vocabulary: `1.0.0`

## Scope

Balance Sheet only, and a **single reporting period**. Every ratio below is computable from a Balance Sheet alone; none requires an Income Statement or a Cash Flow Statement, and none may be added that would. There is no trend, no year-over-year comparison and no industry benchmark - a figure here describes one document at one date.

## How the figures are chosen

> Prefer what the document printed and Module 1 validated. Derive only what was not printed.

The three grand totals are read from the document, where Module 1 located them by anchor and checked the accounting equation against them. Current and non-current subtotals have to be summed from line items instead, because Module 2 excludes every printed subtotal from the extraction and the figure therefore does not exist in the data. Each computed ratio records which basis each of its sides used.

A line item is classified by its **canonical category**, not by the heading it was printed under: many Balance Sheets print no current/non-current headings at all, and heading-based classification would compute nothing on those.

## Precision

Every figure is a `Decimal`; binary floating point is not used anywhere. Sums are exact. A quotient is computed once and rounded once, to 6 decimal places, half-up. Working capital is money and is never rounded. The unrounded numerator and denominator are stored beside every result, so any consumer can re-derive the value at any precision.

## No ratio is ever fabricated

A ratio whose inputs are absent, or whose denominator is zero, is reported `unavailable` with a machine-readable reason. A ratio computed from an incomplete set of line items is reported `partial`, naming the lines it left out and their total, so a reader can bound the true value. Neither is ever a number with the doubt filed off.

Reasons: `missing_section_total`, `no_classified_inputs`, `not_extracted`, `not_representable`, `zero_denominator`

Warnings: `negative_denominator`, `negative_numerator`, `negative_result`, `unmapped_inputs`, `unparsed_inputs`

**No language model is involved in any calculation on this page.** Module 2 uses one to map terminology and is never shown a figure; everything here is deterministic Python.

## The ratios

### `current_ratio`

**Formula:** Current Assets / Current Liabilities

**Unit:** ratio

**Definition.** Whether the assets expected to become cash within a year cover the obligations falling due within the same year. A value below 1 means short-term obligations exceed short-term resources.

**Inputs.**

- **Current Assets** - summed from the normalized line items, because Module 2 excludes printed subtotals from the extraction.

  Fields: `cash_and_cash_equivalents`, `short_term_investments`, `trade_receivables`, `inventory`, `prepaid_expenses`, `other_current_assets`
- **Current Liabilities** - summed from the normalized line items, because Module 2 excludes printed subtotals from the extraction.

  Fields: `trade_payables`, `short_term_borrowings`, `current_tax_liabilities`, `other_current_liabilities`

**Limitations.** Treats every current asset as equally liquid, which inventory and prepaid expenses are not - that is what the quick ratio corrects. Both sides are summed from classified line items rather than read from a printed subtotal, so an unclassified line understates it. Computed from a single reporting period, so it carries no trend and no industry benchmark; a value is only meaningful beside context this system does not hold.

### `quick_ratio`

**Formula:** (Current Assets - Inventory - Prepaid Expenses) / Current Liabilities

**Unit:** ratio

**Definition.** The acid test: short-term cover counting only assets that can be realised without first selling stock. This is the SUBTRACTIVE definition, chosen so that it shares the current ratio's numerator basis and the two can be read side by side. The additive form - cash plus short-term investments plus receivables, over current liabilities - is NOT used here: with a closed six-category current-asset vocabulary it silently drops anything outside the whitelist.

**Inputs.**

- **Quick Assets** - derived from another quantity by removing named categories.

  Fields: Current Assets, less `inventory`, `prepaid_expenses`
- **Current Liabilities** - summed from the normalized line items, because Module 2 excludes printed subtotals from the extraction.

  Fields: `trade_payables`, `short_term_borrowings`, `current_tax_liabilities`, `other_current_liabilities`

**Limitations.** Because it subtracts rather than whitelists, a residual line the document presents as 'other current assets' is counted as quick, which flatters liquidity. The inputs list shows exactly what was included. Computed from a single reporting period, so it carries no trend and no industry benchmark; a value is only meaningful beside context this system does not hold.

### `cash_ratio`

**Formula:** (Cash and Cash Equivalents + Short-term Investments) / Current Liabilities

**Unit:** ratio

**Definition.** The strictest liquidity measure: what could be paid immediately, without collecting a receivable or selling anything. Marketable securities are included, the common presentation; a strict cash-only variant is not used, because it under-reports every sheet that splits deposits out from cash in hand.

**Inputs.**

- **Cash and Equivalents** - summed from the normalized line items, because Module 2 excludes printed subtotals from the extraction.

  Fields: `cash_and_cash_equivalents`, `short_term_investments`
- **Current Liabilities** - summed from the normalized line items, because Module 2 excludes printed subtotals from the extraction.

  Fields: `trade_payables`, `short_term_borrowings`, `current_tax_liabilities`, `other_current_liabilities`

**Limitations.** Deliberately severe - healthy companies routinely run well below 1, because holding enough cash to retire all current liabilities at once is poor capital use rather than prudence. Unavailable, not zero, when neither cash nor short-term investments could be identified. Computed from a single reporting period, so it carries no trend and no industry benchmark; a value is only meaningful beside context this system does not hold.

### `debt_to_equity`

**Formula:** Total Liabilities / Total Equity

**Unit:** ratio

**Definition.** How much of the business is financed by creditors for each unit financed by shareholders. Uses TOTAL LIABILITIES, not borrowings alone: the borrowings-only variant needs a debt/non-debt split that the canonical vocabulary does not draw, and guessing at one would put an invented boundary inside a headline ratio.

**Inputs.**

- **Total Liabilities** - the section total Module 1 located on the document and checked the accounting equation against.

  Fields: `liabilities.total`
- **Total Equity** - the section total Module 1 located on the document and checked the accounting equation against.

  Fields: `equity.total`

**Limitations.** Uninterpretable on its usual scale when equity is negative - the result goes negative and a more insolvent company reports a number closer to zero. The negative_denominator warning marks that case; the value is never clamped, because hiding insolvency is the worst thing this system could do. Computed from a single reporting period, so it carries no trend and no industry benchmark; a value is only meaningful beside context this system does not hold.

### `debt_ratio`

**Formula:** Total Liabilities / Total Assets

**Unit:** ratio

**Definition.** The share of the asset base funded by obligations of any kind. Uses TOTAL LIABILITIES rather than borrowings alone, for the same reason as debt-to-equity: the canonical vocabulary draws no debt/non-debt boundary, and inventing one would put a guess inside a headline ratio.

**Inputs.**

- **Total Liabilities** - the section total Module 1 located on the document and checked the accounting equation against.

  Fields: `liabilities.total`
- **Total Assets** - the section total Module 1 located on the document and checked the accounting equation against.

  Fields: `assets.total`

**Limitations.** Says nothing about when the debt falls due: a sheet financed entirely by twenty-year bonds and one financed entirely by overdrafts report the same figure. Read it beside the current ratio. Computed from a single reporting period, so it carries no trend and no industry benchmark; a value is only meaningful beside context this system does not hold.

### `equity_ratio`

**Formula:** Total Equity / Total Assets

**Unit:** ratio

**Definition.** The share of the asset base funded by shareholders. The complement of the debt ratio on a sheet that balances; both are reported because both are quoted, and their sum is a useful check.

**Inputs.**

- **Total Equity** - the section total Module 1 located on the document and checked the accounting equation against.

  Fields: `equity.total`
- **Total Assets** - the section total Module 1 located on the document and checked the accounting equation against.

  Fields: `assets.total`

**Limitations.** Adds no information beyond the debt ratio when the accounting equation holds. Its value is as a cross-check: if the two do not sum to 1, the section totals disagree with each other. Computed from a single reporting period, so it carries no trend and no industry benchmark; a value is only meaningful beside context this system does not hold.

### `working_capital`

**Formula:** Current Assets - Current Liabilities

**Unit:** currency

**Definition.** The absolute cushion between short-term resources and short-term obligations. A money amount rather than a ratio, so it shows scale where the current ratio shows only proportion.

**Inputs.**

- **Current Assets** - summed from the normalized line items, because Module 2 excludes printed subtotals from the extraction.

  Fields: `cash_and_cash_equivalents`, `short_term_investments`, `trade_receivables`, `inventory`, `prepaid_expenses`, `other_current_assets`
- **Current Liabilities** - summed from the normalized line items, because Module 2 excludes printed subtotals from the extraction.

  Fields: `trade_payables`, `short_term_borrowings`, `current_tax_liabilities`, `other_current_liabilities`

**Limitations.** Being absolute, it cannot be compared between companies of different sizes - that is the current ratio's job. It carries the sheet's printed scale, which this system records and never applies: a sheet printed 'in thousands' yields a figure in thousands. Computed from a single reporting period, so it carries no trend and no industry benchmark; a value is only meaningful beside context this system does not hold.
