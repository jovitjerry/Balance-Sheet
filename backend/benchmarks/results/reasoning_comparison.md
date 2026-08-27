# Module 4 generation and reasoning — full comparison

Four candidates, 14 questions, identical frozen context, `temperature=0`.
Tier 1 is automated and objective. Tier 2 was scored **blind** against the
published rubric before the key was opened.

**A critical failure disqualifies**, per the benchmark's stated rule. Every
score is still published: a table where a disqualified model has good
averages is a finding worth printing, not one to hide.

## Tier 2 — human dimensions (max 28 each: 14 questions × 2)

| Model | Reasoning | Interpretation | Clarity | Critical | Eligible |
|---|---|---|---|---|---|
| `qwen3:8b` | 22/28 (79%) | 19/28 (68%) | 24/28 (86%) | 0 | **yes** |
| `llama3.1:8b` | 17/28 (61%) | 12/28 (43%) | 18/28 (64%) | **1** (Q12) | no |
| `qwen3:4b` | 15/28 (54%) | 14/28 (50%) | 17/28 (61%) | **2** (Q12, Q14) | no |
| `martain7r/finance-llama-8b:q4_k_m` | 13/28 (46%) | 8/28 (29%) | 21/28 (75%) | **3** (Q12, Q13, Q14) | no |

## Tier 1 — automated gates, latency, VRAM

| Model | Gates passed | Grounded | Schema valid | Degenerate | Refusals met | Cold | Warm mean | Warm p95 | VRAM MB |
|---|---|---|---|---|---|---|---|---|---|
| `qwen3:8b` | 12/14 | 14/14 | 14/14 | 1 | 13/14 | 11.53s | 4.16s | 6.05s | 6386 |
| `llama3.1:8b` | 4/14 | 14/14 | 14/14 | 8 | 12/14 | 12.41s | 3.81s | 4.68s | 6080 |
| `qwen3:4b` | 7/14 | 13/14 | 14/14 | 4 | 13/14 | 8.9s | 3.63s | 4.69s | 4082 |
| `martain7r/finance-llama-8b:q4_k_m` | 3/14 | 13/14 | 14/14 | 3 | 12/14 | 13.93s | 5.75s | 9.79s | 6080 |

Cold starts were measured after an explicit `ollama stop`, but all four
models had been pulled minutes earlier and were still in the OS file cache.
Treat these as warm-disk cold starts, not first-boot figures — Module 2
measured `qwen3:8b` at 80.9 s on a cold disk.

## Per question, per model

Reasoning / Interpretation / Clarity, `!` marking a critical failure.

| Question | `qwen3:8b` | `llama3.1:8b` | `qwen3:4b` | `finance-llama-8b:q4_k_m` |
|---|---|---|---|---|
| Q1 direct fact explanation | 2/2/2 | 1/0/1 | 2/2/2 | 1/0/1 |
| Q2 asset composition interpretation | 2/2/2 | 2/1/1 | 2/2/2 | 0/0/0 |
| Q3 liquidity interpretation - THE REP | 1/1/2 | 1/1/1 | 2/2/1 | 2/2/1 |
| Q4 ratio interpretation | 2/2/1 | 2/2/2 | 0/0/0 | 2/2/2 |
| Q5 grounded comparison of supplied fa | 2/1/2 | 1/1/1 | 1/1/1 | 2/1/1 |
| Q6 leverage interpretation | 1/1/1 | 0/0/1 | 0/0/1 | 0/0/2 |
| Q7 working-capital interpretation | 1/1/2 | 0/0/2 | 2/2/2 | 2/1/2 |
| Q8 balance-sheet strengths | 2/2/2 | 1/1/1 | 0/0/0 | 0/0/2 |
| Q9 balance-sheet risks and weaknesses | 2/2/2 | 1/1/2 | 0/0/0 | 0/0/1 |
| Q10 grounded comparison of supplied fa | 2/1/2 | 2/1/1 | 2/2/2 | 2/1/1 |
| Q11 policy/narrative explanation using | 2/2/2 | 2/2/2 | 2/2/2 | 2/1/2 |
| Q12 uncertainty / insufficient informa | 1/1/2 | 0/0/1 ! | 0/0/1 ! | 0/0/2 ! |
| Q13 unsupported / out-of-scope | 2/1/2 | 2/1/1 | 2/1/2 | 0/0/2 ! |
| Q14 unsupported / out-of-scope | 0/0/0 | 2/1/1 | 0/0/1 ! | 0/0/2 ! |

## Known false positive in the grounding gate

`verification.extract_numbers` reads a parenthesised number as the
accountant's negative, which is correct for `(2,300)` on a Balance Sheet and
wrong for an enumerated list marker. An answer written "because: (1) … and
(2) …" yields -1 and -2, neither in context, and is marked ungrounded when
nothing about it is.

It fired once, on **`qwen3:4b` Q3**, whose answer is fully grounded. This is a
defect in shipped Module 4 code, recorded rather than fixed here because the
code is the thing under measurement.

