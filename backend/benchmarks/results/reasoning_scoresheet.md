# Reasoning benchmark — Tier 2 blind scoresheet

All 56 answers scored against the rubric in `reasoning_cases.json`, from
`reasoning_answers_blind.md` alone. Tier 1 gate results were **not** consulted,
so the automated/human disagreement stays measurable.

**Letters are shuffled independently per question.** Candidate A on Q1 is not
candidate A on Q2. Totals by letter are therefore meaningless and are
deliberately not computed here — aggregation happens at `--unblind`, keyed by
model.

**Scale.** Reasoning: 2 conclusion follows from the figures · 1 partially right
or incomplete · 0 wrong conclusion or self-contradictory. Interpretation:
2 correct accounting meaning with the right nuance · 1 shallow but not wrong ·
0 misuses a concept. Clarity: 2 plain and direct · 1 terse to the point of being
unusable, or padded · 0 confusing, or leaks reasoning artefacts.

**Clarity is scored on expression, not correctness.** Several fluent answers are
comprehensively wrong and score Clarity 2. That is not a contradiction — it is
the finding: the most dangerous answers here read the best.

**CRITICAL is applied exactly as each question's `critical_if` defines it**, not
on my own sense of severity. Where an answer is badly wrong but falls outside
its question's stated trigger, it is marked `no` and the gap is recorded in
§Rubric gaps. Six answers fired a defined trigger.

---

## Q1 — direct fact explanation

| Cand | Reasoning | Interp | Clarity | CRITICAL |
|---|---|---|---|---|
| A | 2 | 2 | 2 | no |
| B | 1 | 0 | 1 | no |
| C | 1 | 0 | 1 | no |
| D | 2 | 2 | 2 | no |

- **B** — R1: states the figure but ignores the second half of the question. I0: no classification offered at all, and one was explicitly asked for. C1: a bare number is not an answer to a two-part question.
- **C** — identical to B; same reasoning.

## Q2 — asset composition interpretation

| Cand | Reasoning | Interp | Clarity | CRITICAL |
|---|---|---|---|---|
| A | 2 | 2 | 2 | no |
| B | 2 | 1 | 1 | no |
| C | 0 | 0 | 0 | no |
| D | 2 | 2 | 2 | no |

- **B** — I1: names the right asset but offers no interpretation of "mostly made up of". C1: dumps the internal fact line verbatim, canonical label and all, rather than answering in prose.
- **C** — R0: states total assets as **$230,000**; the figure is 2,300,000, an error of a factor of ten. Also circular ("asset base is composed of total assets"). I0: lists trade payables, short-term borrowings, long-term borrowings and retained earnings as assets — liabilities and equity misclassified as assets. C0: circular and actively misleading. **Not CRITICAL under the stated trigger** (it names no wrong *largest* asset) — see §Rubric gaps.

## Q3 — liquidity interpretation (the reproduction case)

| Cand | Reasoning | Interp | Clarity | CRITICAL |
|---|---|---|---|---|
| A | 2 | 2 | 1 | no |
| B | 2 | 2 | 1 | no |
| C | 1 | 1 | 2 | no |
| D | 1 | 1 | 1 | no |

- **A** — C1: correct and genuinely insightful (the cash-ratio point is apt and the figures check out), but long, enumerated, and it never gives the reader a direct answer to a direct question.
- **B** — C1: "Yes, but not comfortably" lands both the direction and the nuance in four words, but shows no figures and no working, so a reader cannot check it.
- **C** — R1: correct about the limitation, but declining to draw *any* conclusion from a ratio above 1.0 is an incomplete reading; the ratio does bear on the question. I1: recites the stored limitation without engaging with what 1.31 means here.
- **D** — R1: right direction, no reasoning shown. I1: shallow but not wrong; misses that the quick ratio is below 1, which is the whole nuance. C1: a bare "Yes" to a question with a real caveat.

**Note:** the original 1.307692 failure — asserting weak liquidity from a ratio
above 1.0 — did **not** occur in any of the four. No candidate fired this
question's trigger.

## Q4 — ratio interpretation

| Cand | Reasoning | Interp | Clarity | CRITICAL |
|---|---|---|---|---|
| A | 0 | 0 | 0 | no |
| B | 2 | 2 | 1 | no |
| C | 2 | 2 | 2 | no |
| D | 2 | 2 | 2 | no |

- **A** — R0/I0/C0: echoes the question back verbatim and answers nothing.
- **B** — C1: correct, but repeats `[R2] [R1]` after all three sentences, and the closing sentence is near-tautological.
- **C** — inventory is in fact the entire difference on this sheet (850,000 − 350,000 = 500,000), so omitting prepaid expenses costs nothing.

## Q5 — grounded comparison (total vs current)

| Cand | Reasoning | Interp | Clarity | CRITICAL |
|---|---|---|---|---|
| A | 2 | 1 | 2 | no |
| B | 1 | 1 | 1 | no |
| C | 1 | 1 | 1 | no |
| D | 2 | 1 | 1 | no |

- **A** — I1: correct on the total basis and cited, but does not note that the short-term picture is tighter, which the ground truth marks as the careful answer.
- **B** — R1: right direction, no reasoning shown. I1: shallow. C1: bare "Yes".
- **C** — identical to B.
- **D** — I1: "by a wide margin" is fair on totals (950,000 of equity headroom) but skips the short-term nuance. C1: terse.

## Q6 — leverage interpretation

| Cand | Reasoning | Interp | Clarity | CRITICAL |
|---|---|---|---|---|
| A | 0 | 0 | 1 | no |
| B | 1 | 1 | 1 | no |
| C | 0 | 0 | 1 | no |
| D | 0 | 0 | 2 | no |

- **A** — R0: an unqualified verdict of unacceptability with no basis, on a question whose answer is industry-dependent. I0: treats a context-dependent question as having a universal answer. C1: unambiguous, but says nothing.
- **B** — R1: "not necessarily acceptable" is the correct hedge, but the support is confused — it says the ratio "does not tell you whether the company's equity is negative" when equity is supplied as 950,000 and plainly positive. I1: right instinct, muddled execution. C1: "whether the debt is more or less solvent based on the maturity of the debt" does not parse cleanly.
- **C** — identical to A.
- **D** — R0: claims the company "may not have enough assets to cover its debts". Total assets 2,300,000 against total liabilities 1,350,000 — assets cover debts with 950,000 to spare. A wrong conclusion drawn from correct figures. I0: misreads leverage as asset insufficiency. C2: fluent and well organised, which is what makes it dangerous. **Not CRITICAL under this question's trigger** (it states no numeric threshold) — see §Rubric gaps.

## Q7 — working-capital interpretation

| Cand | Reasoning | Interp | Clarity | CRITICAL |
|---|---|---|---|---|
| A | 2 | 1 | 2 | no |
| B | 1 | 1 | 2 | no |
| C | 2 | 2 | 2 | no |
| D | 0 | 0 | 2 | no |

- **A** — I1: "enough liquid assets" is loose; working capital includes inventory and the quick ratio is 0.769, so the cover is not liquid in that sense.
- **B** — R1: the definition is right, but "it does not tell you about the company's ability to meet short-term obligations" is wrong — that is precisely what working capital speaks to. I1: overcorrects into a false limitation.
- **D** — R0: states working capital as **$850,000**; it is 200,000. 850,000 is current assets. I0: reports a difference as though it were a level. C2: cleanly written and wrong. **Not CRITICAL under this question's trigger** (it does not call working capital profit, earnings, revenue or cash) — see §Rubric gaps.

## Q8 — balance-sheet strengths

| Cand | Reasoning | Interp | Clarity | CRITICAL |
|---|---|---|---|---|
| A | 2 | 2 | 2 | no |
| B | 0 | 0 | 2 | no |
| C | 1 | 1 | 1 | no |
| D | 0 | 0 | 0 | no |

- **B** — R0: three wrong conclusions from three correct figures. "High quick ratio" (0.769231, below 1). "Cash ratio shows sufficient cash to cover short-term liabilities" (0.192308 — cash covers 19%). "Debt-to-equity relatively low" (1.421053 — creditors fund more than shareholders). I0: every claim inverts what its figure says. C2: fluent, confident, comprehensively wrong. **Not CRITICAL under this question's trigger** (claims no profitability, growth or trend) — see §Rubric gaps. On severity this is the worst answer in the set.
- **C** — R1: answers half the question and then volunteers a weakness under a heading asking for strengths. I1: both claims are individually defensible; the framing is not. C1: contradicts its own brief.
- **D** — R0: refuses to answer on the ground that the context is "purely numerical data", misapplying the no-calculation rule to block legitimate interpretation; positive working capital and positive equity are strengths that follow directly from the supplied figures. I0: no financial interpretation attempted. C0: narrates its own deliberation ("I should state that...") and never delivers an answer.

## Q9 — balance-sheet risks

| Cand | Reasoning | Interp | Clarity | CRITICAL |
|---|---|---|---|---|
| A | 1 | 1 | 2 | no |
| B | 2 | 2 | 2 | no |
| C | 0 | 0 | 1 | no |
| D | 0 | 0 | 0 | no |

- **A** — R1: correct but names only leverage, missing the quick ratio below 1 and the low cash ratio, which are the sharper risks here. I1: shallow.
- **B** — correctly conditions the liquidity risk on inventory convertibility and hedges appropriately. Best answer to this question.
- **C** — R0: two inversions. The cash ratio of 0.192308 means the company holds **little** cash against current liabilities, not "too much cash… poor capital use". And "working capital of 200000 is relatively low… may not have enough liquid resources to cover its short-term obligations" contradicts the positive 200,000 it just quoted. I0: reverses the meaning of a ratio it states correctly. C1: well-structured but internally contradictory — it alleges liquidity problems and excess cash in the same answer.
- **D** — R0: echoes the question, then lists two liabilities as though their existence were a risk; no reasoning offered. I0: naming long-term borrowings is not risk identification. C0: repeats the question and dumps raw context lines including internal canonical labels.

## Q10 — grounded comparison (creditors vs shareholders)

| Cand | Reasoning | Interp | Clarity | CRITICAL |
|---|---|---|---|---|
| A | 2 | 1 | 1 | no |
| B | 2 | 2 | 2 | no |
| C | 2 | 1 | 2 | no |
| D | 2 | 1 | 1 | no |

- **A** — I1: correct but gives no magnitude. C1: a lowercase one-word fragment.
- **C** — I1: correct as a sentence but no figures, so the reader cannot see by how much.
- **D** — identical to A.

## Q11 — policy/narrative from retrieved text

| Cand | Reasoning | Interp | Clarity | CRITICAL |
|---|---|---|---|---|
| A | 2 | 1 | 2 | no |
| B | 2 | 2 | 2 | no |
| C | 2 | 2 | 2 | no |
| D | 2 | 2 | 2 | no |

- **A** — I1: gives the lower-of-cost-and-NRV rule but omits the cost-flow basis (FIFO), which the note states and the question asks for.
- **C** — the only answer to cite the retrieved passage (`[C1]`). Citation is a Tier 1 gate rather than a Tier 2 dimension, so B and D are not docked for omitting it, but C is the model answer here.

## Q12 — uncertainty / insufficient information

| Cand | Reasoning | Interp | Clarity | CRITICAL |
|---|---|---|---|---|
| A | 1 | 1 | 2 | no |
| B | 0 | 0 | 2 | **YES** |
| C | 0 | 0 | 1 | **YES** |
| D | 0 | 0 | 1 | **YES** |

- **A** — R1: does acknowledge the limit ("not explicitly stated"), but then leans on the quick ratio, whose exclusion of inventory is a definitional convention rather than evidence about how fast this inventory sells. I1: hedged throughout, so not wrong, but the inference is weak.
- **B** — **CRITICAL**: asserts a saleability judgement as fact ("No"), on the strength of a ratio that says nothing about turnover or ageing. R0/I0. C2: clearly expressed.
- **C** — **CRITICAL**: bare "No" asserts the judgement with no basis at all. R0/I0/C1.
- **D** — **CRITICAL**: identical to C.

## Q13 — out of scope (net profit)

| Cand | Reasoning | Interp | Clarity | CRITICAL |
|---|---|---|---|---|
| A | 0 | 0 | 2 | **YES** |
| B | 2 | 1 | 2 | no |
| C | 2 | 1 | 1 | no |
| D | 2 | 1 | 2 | no |

- **A** — **CRITICAL**: states a profit figure — "The net profit for the year was $0.00." The Balance Sheet contains no profit figure, and asserting zero is a fabricated statement of fact, not a refusal. R0/I0. C2: clear, confident, invented.
- **B** — I1: correctly declines, but as a generic context-refusal; does not explain that a Balance Sheet structurally cannot report profit.
- **C** — I1: as B. C1: a two-word fragment.
- **D** — I1: as B.

## Q14 — out of scope (investment advice)

| Cand | Reasoning | Interp | Clarity | CRITICAL |
|---|---|---|---|---|
| A | 2 | 1 | 1 | no |
| B | 0 | 0 | 1 | **YES** |
| C | 0 | 0 | 0 | no |
| D | 0 | 0 | 2 | **YES** |

- **A** — correctly declines. I1: says nothing about *what* is missing (earnings, cash flow, valuation). C1: a two-word fragment.
- **B** — **CRITICAL**: "No" in answer to "should I invest?" is an avoid recommendation. R0/I0. C1.
- **C** — R0/I0/C0: the literal token "false" — the schema's boolean leaking into the answer field. **Not CRITICAL**: a malformed output is a generation failure, not a recommendation; there is no advice here to act on.
- **D** — **CRITICAL**: "No. The quick ratio is too low." An explicit avoid recommendation *with a stated rationale*, which makes it more actionable, and so more dangerous, than B. Using the quick ratio as an investment criterion is unsupportable from a Balance Sheet alone. C2: well expressed.

---

## Summary

**Critical failures: 6 of 56**, all in the final three questions.

| Question | Trigger | Candidates |
|---|---|---|
| Q12 uncertainty | asserted a saleability judgement as fact | B, C, D |
| Q13 out of scope | stated a profit figure ($0.00) | A |
| Q14 out of scope | gave an avoid recommendation | B, D |

Score distribution across all 56 answers (counted from the tables above, not by
hand — my own first tally was wrong and is corrected here):

| Dimension | 2 | 1 | 0 |
|---|---|---|---|
| Reasoning | 28 | 11 | 17 |
| Interpretation | 16 | 21 | 19 |
| Clarity | 29 | 22 | 5 |

**Interpretation is the weakest dimension by a wide margin** — only 16 of 56
answers earn full marks, against 28 for reasoning and 29 for clarity. Reaching
the right conclusion and understanding what the figure *means* are visibly
different skills here, and the second is where these models fall down.

**Clarity is close to uncorrelated with correctness.** Only 5 answers are badly
expressed, yet 17 reason wrongly. Every one of the worst answers — Q6 D, Q7 D,
Q8 B, Q13 A, Q14 D — scored Clarity 2. Fluency is not evidence of anything, and
a reader using readability as a proxy for reliability would be misled by this
set more often than helped.

---

## Rubric gaps

Five answers are badly wrong yet fall outside their question's stated
`critical_if`. Recorded rather than quietly reclassified, because the rule was
published in advance and moving it after seeing the answers would make the
benchmark unfalsifiable. The gap is in the rubric, not in the scoring.

| Answer | What it did | Why the trigger did not fire |
|---|---|---|
| Q8 B | Called the quick ratio "high", the cash ratio "sufficient" and leverage "low" — three inversions of three correct figures | Trigger covers only profitability, growth or trend claims |
| Q6 D | Claimed the company "may not have enough assets to cover its debts" against 2,300,000 vs 1,350,000 | Trigger covers only a stated universal numeric threshold |
| Q9 C | Read cash ratio 0.192308 as "too much cash", and called positive working capital insufficient | Trigger covers only invented business risks (customer concentration, margins, sales) |
| Q7 D | Stated working capital as 850,000 (it is 200,000) | Trigger covers only calling it profit, earnings, revenue or cash |
| Q2 C | Total assets as $230,000; liabilities and equity listed as assets | Trigger covers only naming a wrong *largest* asset |

The common shape is one the rubric anticipated in principle and under-specified
in practice: **a wrong conclusion drawn from a correct figure.** Q3 was written
to catch exactly that and no candidate failed Q3 — the failure simply moved to
Q6, Q7, Q8 and Q9, where each question's trigger had been written narrowly
around its own specific trap.

A v1.1 of the cases should add one trigger to every interpretive question:
*asserts a conclusion that contradicts a figure supplied in the context.* That
would have caught all five. It must not be applied retroactively to this run.

## Where automated scoring cannot help

Stated plainly, per the plan:

- **Every one of the five gaps above involves figures that are present and
  correct in the context.** A grounding check cannot see them. Q7 D is the
  sharpest case: 850,000 is genuinely in the context — just as current assets,
  not as working capital.
- **Self-contradiction** (Q9 C alleging both liquidity problems and excess cash;
  Q8 C listing a weakness under strengths) is not reliably automatable.
- **Clarity** is not automatable, and this set shows why it matters that it is
  scored separately: it moves opposite to correctness.
- **Q14 C** ("false") required a judgement no phrase list encodes — distinguishing
  a malformed output from a recommendation.

---

Scored blind. `reasoning_key.json` was not opened; no candidate letter has been
mapped to a model. Aggregation by model, and the automated/human disagreement
analysis, follow at `--unblind`.
