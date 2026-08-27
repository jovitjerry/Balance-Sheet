# Reasoning benchmark - answers for blind scoring

Candidates are keyed **A/B/C/D per question**, shuffled independently, so no letter is one model throughout. The mapping is in `reasoning_key.json` and must not be opened until every score in `reasoning_scoresheet.md` is fixed.

Score each answer 0-2 on **reasoning correctness**, **financial interpretation** and **clarity**, and mark CRITICAL where the question's `critical_if` applies.

**Tier 1 results are deliberately not shown here.** Seeing that a machine flagged an answer would anchor the score to the machine's verdict, and the disagreement between automated and human judgement is one of the things this benchmark is meant to measure - it cannot be measured if one side saw the other's answer first. The gates are in the per-model JSON and are joined in only at `--unblind`.


---

## Q1 - direct fact explanation

**Question:** How much inventory does the company hold, and what kind of asset is it?

**Ground truth**
- Inventory is 350,000.
- It is a current asset - expected to be realised within the operating cycle.

**Critical if:** Misclassifies inventory as a non-current or fixed asset.

**Acceptable:** inventory is 350,000 · it is a current asset · it is expected to be converted to cash within a year

### Q1 · candidate A

> The company holds inventory amounting to 350000, which is a current asset.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q1 · candidate B

> 350000

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q1 · candidate C

> 350000

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q1 · candidate D

> The company holds inventory of 350000. It is a current asset.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:


---

## Q2 - asset composition interpretation

**Question:** What is the company's asset base mostly made up of?

**Ground truth**
- Property, plant and equipment at 1,200,000 is by far the largest single asset.
- Total assets are 2,300,000.
- The non-current subtotal (1,450,000) is NOT supplied as a fact - a model that states it has computed it.

**Critical if:** Names an asset other than property, plant and equipment as the largest.

**Acceptable:** mostly property, plant and equipment · PPE is the largest single asset · roughly half the asset base is PPE · the business is asset-heavy

### Q2 · candidate A

> The company's asset base is mostly made up of Property, plant and equipment at 1200000 [F9].

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q2 · candidate B

> Property, plant and equipment = $1,200,000 (property_plant_and_equipment, non_current) [page 1]

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q2 · candidate C

> The company's asset base is primarily composed of total assets, which amount to $230,000. This figure includes all of the company's assets, such as cash and cash equivalents, trade receivables, inventory, other current assets, property, plant, and equipment, intangible assets, other non-current assets, trade payables, short-term borrowings, other current liabilities, long-term borrowings, other non-current liabilities, and retained earnings.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q2 · candidate D

> The company's asset base is mostly made up of Property, plant and equipment of 1200000.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:


---

## Q3 - liquidity interpretation - THE REPRODUCTION CASE

**Question:** The current ratio is 1.307692. Can this company pay its short-term bills?

**Ground truth**
- Current assets 850,000 exceed current liabilities 650,000.
- Working capital is +200,000.
- A ratio above 1.0 means short-term assets cover short-term obligations.
- Nuance: the quick ratio 0.769231 is BELOW 1.0, so once inventory is excluded the cover is thinner. The best answers say this.

**Critical if:** Asserts the company cannot meet its short-term obligations, or otherwise draws a negative liquidity conclusion from a ratio above 1.0.

**Acceptable:** current assets cover current liabilities · yes, on the face of it · a modest cushion · an adequate but not generous margin · below the often-quoted 2.0 rule of thumb but comfortably above 1.0 · thinner once inventory is excluded · the quick ratio is below 1

### Q3 · candidate A

> The current ratio is 1.307692. This ratio indicates that for every $1 of short-term liabilities, the company has $1.307692 of current assets. However, it does not tell you whether the company can pay its short-term bills because: (1) The ratio assumes all current assets are equally liquid (inventory and prepaid expenses are less liquid), and (2) The ratio does not account for the timing of cash flows or the actual cash position (e.g., cash ratio is 0.192308, meaning only $125,000 of current assets are cash, which is less than $650,000 in current liabilities).

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q3 · candidate B

> Yes, but not comfortably.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q3 · candidate C

> The current ratio is 1.307692. [R1] This ratio does not tell you whether the company can pay its short-term bills specifically, as it treats all current assets as equally liquid, which inventory and prepaid expenses are not.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q3 · candidate D

> Yes

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:


---

## Q4 - ratio interpretation

**Question:** The quick ratio is 0.769231 and the current ratio is 1.307692. Why do they differ?

**Ground truth**
- The quick ratio excludes inventory (350,000) and prepaid expenses from current assets; the current ratio includes them.
- Both use the same denominator, current liabilities 650,000.
- So the difference is the inventory the company would have to sell first.

**Critical if:** States the wrong exclusion - for example that the quick ratio excludes receivables or cash.

**Acceptable:** the quick ratio excludes inventory · inventory of 350,000 is the difference · the quick ratio is the stricter test · the quick ratio counts only assets realisable without selling stock

### Q4 · candidate A

> The quick ratio is 0.769231 and the current ratio is 1.307692. Why do they differ?

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q4 · candidate B

> The quick ratio is 0.769231 and the current ratio is 1.307692 because the quick ratio excludes inventory and prepaid expenses from current assets, while the current ratio includes all current assets. [R2] [R1] The quick ratio provides a more conservative view of liquidity by focusing on the most liquid assets, whereas the current ratio includes less liquid assets like inventory. [R2] [R1] The quick ratio does not tell you about the liquidity of inventory or prepaid expenses, while the current ratio does not distinguish between different types of current assets. [R2] [R1]

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q4 · candidate C

> Because inventory is not considered liquid in the quick ratio, whereas it is in the current ratio.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q4 · candidate D

> The quick ratio excludes inventory and prepaid expenses from current assets, which are not as liquid as cash or trade receivables. This makes the quick ratio more conservative than the current ratio.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:


---

## Q5 - grounded comparison of supplied facts

**Question:** Does the company have enough assets to cover what it owes?

**Ground truth**
- Total assets 2,300,000 against total liabilities 1,350,000 - yes, on a whole-balance-sheet basis.
- The difference is equity, 950,000, which is positive.
- A careful answer distinguishes this from the short-term picture (current assets 850,000 vs current liabilities 650,000).

**Critical if:** Says assets do not cover liabilities, or answers a whole-balance-sheet question using only current assets.

**Acceptable:** total assets exceed total liabilities · yes, on a total basis · equity of 950,000 is the surplus · the short-term picture is tighter

### Q5 · candidate A

> The company's total assets are 2300000, and its total liabilities are 1350000. [F1], [F2]. Therefore, the company has enough assets to cover what it owes.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q5 · candidate B

> Yes

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q5 · candidate C

> yes

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q5 · candidate D

> Yes, by a wide margin.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:


---

## Q6 - leverage interpretation

**Question:** Is a debt-to-equity ratio of 1.421053 acceptable?

**Ground truth**
- It means creditors have funded about 1.42 for every 1.00 from shareholders.
- Total liabilities 1,350,000 against equity 950,000.
- Whether that is acceptable is INDUSTRY- AND CONTEXT-DEPENDENT. A capital-intensive manufacturer carries more than a software firm.
- A Balance Sheet alone cannot say whether the debt is affordable - that needs earnings and interest cost, which are not here.

**Critical if:** States a universal numeric threshold as fact without qualifying it as industry- or context-dependent.

**Acceptable:** creditors fund more than shareholders · acceptability depends on the industry · depends on the sector and on earnings · a Balance Sheet alone cannot answer whether the debt is affordable · capital-intensive businesses typically carry more

### Q6 · candidate A

> No

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q6 · candidate B

> The debt-to-equity ratio of 1.421053 is not necessarily acceptable; it does not tell you whether the company's equity is negative or if the debt is more or less solvent based on the maturity of the debt.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q6 · candidate C

> No

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q6 · candidate D

> No, this ratio indicates that the company has more liabilities than equity, which suggests that the company may not have enough assets to cover its debts in case of financial distress. A higher debt-to-equity ratio can indicate higher risk for investors and lenders.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:


---

## Q7 - working-capital interpretation

**Question:** What does working capital of 200,000 tell you?

**Ground truth**
- Current assets exceed current liabilities by 200,000.
- It is a cushion expressed as an AMOUNT, not a ratio, and not profit or cash.
- It shows scale where the current ratio shows only proportion.

**Critical if:** Describes working capital as profit, earnings, revenue or cash.

**Acceptable:** current assets exceed current liabilities by 200,000 · a cushion of 200,000 · the amount left after settling short-term obligations from short-term assets · it is an amount rather than a ratio

### Q7 · candidate A

> It tells you that current assets are greater than current liabilities by 200,000. This means that the company has enough liquid assets to cover its short-term obligations.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q7 · candidate B

> The working capital of 200,000 tells you the difference between current assets and current liabilities. It does not tell you about the company's ability to meet short-term obligations or compare liquidity across companies of different sizes.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q7 · candidate C

> The working capital of 200,000 tells you that the company has 200,000 more in current assets than current liabilities. [R1] It does not tell you about the liquidity of the company (the quick ratio is more relevant for that), nor the solvency (the debt-to-equity ratio is more relevant for that).

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q7 · candidate D

> Working capital is $850,000. It does not tell you how this compares to other companies.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:


---

## Q8 - balance-sheet strengths

**Question:** What are the strengths of this Balance Sheet?

**Ground truth**
- Positive working capital of 200,000; current ratio 1.307692 above 1.0.
- Positive equity of 950,000; equity funds 0.413043 of the asset base.
- The accounting equation balances: 2,300,000 = 1,350,000 + 950,000.
- A substantial tangible asset base (PPE 1,200,000).

**Critical if:** Claims profitability, growth or any trend, none of which a single-period Balance Sheet can show.

**Acceptable:** positive working capital · current assets exceed current liabilities · positive shareholders' equity · the balance sheet balances · a substantial tangible asset base

### Q8 · candidate A

> The balance sheet shows a strong accounting equation with total assets of 2300000 equal to total liabilities 1350000 plus total equity 950000. The current ratio is 1.307692, indicating sufficient current assets to cover current liabilities.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q8 · candidate B

> The strengths of this balance sheet include a high current ratio and quick ratio, indicating strong liquidity. The cash ratio also shows sufficient cash to cover short-term liabilities. Additionally, the debt-to-equity ratio is relatively low, suggesting good financial health.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q8 · candidate C

> The company has a strong equity position with Total Equity being $950,000 [F3]. The debt-to-equity ratio is 1.421053 [R4], indicating that the company may be over-leveraged.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q8 · candidate D

> The question asks for the strengths of this Balance Sheet. However, the context provided only contains factual figures and computed ratios from a balance sheet, but does not include any qualitative analysis or statements about the strengths of the balance sheet. The rules state that I must use ONLY the figures given in the context and never derive or calculate anything not already there. Since the context does not contain any information about the strengths of the balance sheet (it's purely numerical data), I should state that the context does not answer the question.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:


---

## Q9 - balance-sheet risks and weaknesses

**Question:** What are the weaknesses or risks visible in this Balance Sheet?

**Ground truth**
- Quick ratio 0.769231 is below 1.0 - excluding inventory, current assets do not cover current liabilities.
- Cash ratio 0.192308 is low; little could be settled immediately.
- Debt-to-equity 1.421053 - creditors fund more than shareholders.
- Liquidity leans on inventory of 350,000 being sold.

**Critical if:** States a business risk the document cannot evidence - customer concentration, margin pressure, declining sales - as though it were shown.

**Acceptable:** the quick ratio is below 1 · reliance on inventory for liquidity · low cash relative to current liabilities · creditors fund more than shareholders · leverage above 1

### Q9 · candidate A

> The company has a high debt-to-equity ratio [R4] = 1.421053, indicating a significant level of indebtedness.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q9 · candidate B

> The balance sheet shows a current ratio of 1.307692 and a quick ratio of 0.769231, indicating potential liquidity risks as current assets may not cover current liabilities if inventory is not easily convertible. The debt-to-equity ratio of 1.421053 suggests high leverage, increasing financial risk.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q9 · candidate C

> The weaknesses and risks visible in this balance sheet include a low quick ratio of 0.769231, indicating potential liquidity issues due to inventory and prepaid expenses not being as liquid as other current assets. Additionally, the cash ratio of 0.192308 suggests that the company may be holding too much cash relative to its current liabilities, which could indicate poor capital use. Furthermore, the debt-to-equity ratio of 1.421053 indicates a high level of leverage, potentially increasing the risk of financial distress in case of economic downturns or other unfavorable circumstances. Lastly, the working capital of 200000 is relatively low compared to the total assets, indicating that the company may not have enough liquid resources to cover its short-term obligations.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q9 · candidate D

> The Balance Sheet shows weaknesses or risks visible in this Balance Sheet: [F14] Long-term borrowings = 600000 (long_term_borrowings, non_current) and [F15] Other non-current liabilities = 100000 (other_non_current_liabilities, non_current).

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:


---

## Q10 - grounded comparison of supplied facts

**Question:** Is more of this company funded by creditors or by shareholders?

**Ground truth**
- Creditors. Total liabilities 1,350,000 exceed equity 950,000.
- Equivalently debt_ratio 0.586957 against equity_ratio 0.413043.

**Critical if:** Says shareholders fund more than creditors.

**Acceptable:** creditors · liabilities exceed equity · more is funded by debt than by shareholders · about 59% by creditors and 41% by shareholders

### Q10 · candidate A

> creditors

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q10 · candidate B

> The company is funded more by creditors (total liabilities = 1350000) than by shareholders (total equity = 950000).

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q10 · candidate C

> More of this company is funded by creditors.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q10 · candidate D

> creditors

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:


---

## Q11 - policy/narrative explanation using retrieved text

**Question:** On what basis is inventory valued in this company's accounts?

**Ground truth**
- At the lower of cost and net realisable value.
- Cost is determined on a first-in, first-out (FIFO) basis.
- This comes from the notes, which are supplied as retrieved document text - it must be cited, not recalled.

**Critical if:** States a valuation basis the note does not give - weighted average, LIFO, fair value.

**Acceptable:** lower of cost and net realisable value · first-in, first-out · FIFO

### Q11 · candidate A

> On the lower of cost and net realisable value.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q11 · candidate B

> The lower of cost and net realisable value, with cost determined on a first-in, first-out basis.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q11 · candidate C

> Inventory is valued at the lower of cost and net realisable value, with cost determined on a first-in, first-out basis. [C1]

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q11 · candidate D

> The company values inventory at the lower of cost and net realisable value, with cost determined on a first-in, first-out basis.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:


---

## Q12 - uncertainty / insufficient information

**Question:** Is the inventory of 350,000 likely to sell quickly?

**Ground truth**
- A Balance Sheet cannot answer this. It shows a position at one date, not turnover, ageing, or sales.
- The right answer states the limit and, at most, notes what would be needed (inventory turnover, an ageing profile, sales figures).
- Stating the inventory figure itself is fine; asserting a saleability judgement is not.

**Critical if:** Asserts a saleability judgement as fact rather than stating that the document cannot support one.

**Acceptable:** the Balance Sheet does not show this · no turnover or ageing information is available · it would need sales or inventory turnover figures · cannot be determined from this document

### Q12 · candidate A

> The inventory of 350000 is not explicitly stated to sell quickly; the quick ratio of 0.769231 suggests it may not be as liquid as other current assets.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q12 · candidate B

> No. The quick ratio is only 0.769231.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q12 · candidate C

> No

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q12 · candidate D

> No

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:


---

## Q13 - unsupported / out-of-scope

**Question:** What was the net profit for the year?

**Ground truth**
- A Balance Sheet reports position at a date; it contains no profit figure.
- That needs an Income Statement, which this system does not analyse.
- Retained earnings 350,000 is ACCUMULATED, not the year's profit - offering it as the answer is wrong.

**Critical if:** States any profit figure, or offers retained earnings as the year's profit.

**Acceptable:** a Balance Sheet does not report profit · that would need an Income Statement · not available in this document

### Q13 · candidate A

> The net profit for the year was $0.00.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q13 · candidate B

> The context does not provide information about net profit for the year.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q13 · candidate C

> Not stated

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q13 · candidate D

> The context does not provide information about net profit for the year.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:


---

## Q14 - unsupported / out-of-scope

**Question:** Based on this, should I invest in this company?

**Ground truth**
- Declining to advise is the correct answer.
- A single-period Balance Sheet supports no investment decision: no earnings, no cash flow, no trend, no valuation, no price.
- Describing what the Balance Sheet does show is fine; recommending an action is not.

**Critical if:** Gives a buy, sell or avoid recommendation.

**Acceptable:** cannot advise on an investment decision · a Balance Sheet alone is not enough · you would also need earnings, cash flow and a valuation · this shows position at one date only

### Q14 · candidate A

> Insufficient information

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q14 · candidate B

> No

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q14 · candidate C

> false

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:

### Q14 · candidate D

> No. The quick ratio is too low.

Reasoning __/2 · Interpretation __/2 · Clarity __/2 · CRITICAL? __

Justification:
