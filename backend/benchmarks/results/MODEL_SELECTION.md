# Model selection — Module 2 terminology normalization

**Selected: `qwen3:8b`** · decided 2026-08-26 · taxonomy `1.0.0` · cases `1.0.0`

This decision covers **Module 2 only** — mapping a printed line-item label onto
the canonical vocabulary. It does not settle Module 4. See *Scope* below.

## Evidence

Four candidates, 75 labelled cases, on the development machine (RTX 4060 Laptop,
8 GB VRAM), Ollama, `temperature=0`, `num_ctx=4096`, one run each.

| Model | Accuracy | Correct abstention | Over-answered | Cold | Warm mean | Warm p95 | VRAM (MB) |
|---|---|---|---|---|---|---|---|
| **qwen3:8b** | **97%** (60/62) | 54% (7/13) | 46% | 80.9s | **4.15s** | **4.61s** | 6460 |
| qwen3:4b | 95% (59/62) | **62%** (8/13) | **38%** | 15.7s | 4.68s | 5.14s | **4160** |
| llama3.1:8b | 95% (59/62) | 46% (6/13) | 54% | 18.1s | 4.39s | 4.86s | 6156 |
| martain7r/finance-llama-8b:q4_k_m | 95% (59/62) | **15%** (2/13) | **85%** | 11.5s | 4.85s | 6.06s | 5141 |

Per group, correct/total:

| Model | standard | synonym | abbrev | unusual | ambiguous | unknown |
|---|---|---|---|---|---|---|
| qwen3:8b | 20/20 | 25/26 | 8/8 | 7/8 | 2/8 | 5/5 |
| qwen3:4b | 20/20 | 23/26 | 8/8 | 8/8 | 3/8 | 5/5 |
| llama3.1:8b | 20/20 | 24/26 | 8/8 | 7/8 | 1/8 | 5/5 |
| finance-llama | 19/20 | 24/26 | 8/8 | 8/8 | 0/8 | 2/5 |

Every model returned valid JSON with a valid canonical label on every case:
invalid-label rate, malformed rate and section-mismatch rate were 0% throughout.
That is the enum-constrained decoding working as designed, not a distinction
between models.

## Why this model

1. **Highest measured normalization accuracy** — 97% on the 62 cases that have a
   right answer.
2. **Clean output.** No visible chain-of-thought leakage under the response
   schema. `qwen3:4b` leaks several hundred words of deliberation and a
   `</think>` tag in free-text mode; `finance-llama` appends hallucinated
   follow-up questions to most answers.
3. **Fastest steady-state latency** — 4.15s mean, 4.61s p95 per label, the best
   of the four.
4. **Fits the hardware.** 6460 MB on an 8 GB card with `num_ctx` capped at 4096.
   Tight but stable; no spill to system RAM was observed across 75 cases.
5. **The finance-specific model did not outperform it.** `finance-llama-8b`
   matched none of its accuracy edge and was the **worst** on abstention by a
   wide margin: it answered *every* ambiguous case and 3 of 5 nonsense ones,
   mapping `Schedule 14` to `cash_and_cash_equivalents` and `qwerty asdf` to
   `other_current_assets`. Being tuned on financial text did not help with
   label-to-taxonomy mapping, which was the hypothesis this candidate existed to
   test.

## Limitations of this evidence

Recorded so the decision can be revisited on its merits rather than re-argued
from memory.

- **The accuracy lead is one case.** 60/62 against 59/62. At this sample size and
  with a single run per model, that gap is not statistically meaningful on its
  own. Points 2-5 above are what carry the decision.
- **Abstention is not this model's strength.** It declined only 2 of 8 genuinely
  ambiguous labels; `qwen3:4b` declined 3. Every over-answered case reaches the
  document as a confident category, and the section-fit check will not catch one
  that is plausible for its section. Watch `normalization_summary` on real
  filings.
- **80.9s cold start** — the slowest of the four by 4x, paid on the first request
  after Ollama loads the model, not per document. `qwen3:4b` costs 15.7s and
  2.3 GB less VRAM; if cold latency or headroom becomes a problem, it is the
  obvious alternative and its accuracy deficit is within the noise above.
- **One run, `temperature=0`.** No repeat-variance was measured. Three repeat
  runs of `qwen3:8b` and `qwen3:4b` would establish whether the one-case lead is
  real.

## Scope — what this does not decide

**Module 4 is a separate choice and must be evaluated separately.** The
Module 4-style Q&A benchmark (`qa_comparison.md`, answers in `qa_answers.md`)
does **not** support this model for explanation work: on those 10 questions
`qwen3:8b` summed current assets as 550,000 instead of 850,000 and concluded the
company could not pay its short-term bills — the opposite of the truth — and on
another question stated the correct method and then declared it could not be
applied. `qwen3:4b` was the only candidate that made no false factual statement,
though its raw output is unusable without stripping its reasoning.

Three of the four models made arithmetic errors on a Balance Sheet containing
fifteen numbers. That is direct support for the standing rule that **financial
calculations are never delegated to the LLM** — and the reason those errors do
not disqualify this model for Module 2, which shows it no figures at all.

The model stays configurable: `OLLAMA_MODEL` in `.env`, reached through the
`LlmProvider` seam in `core/llm/`. Module 4 can select a different one without
touching Module 2.

## Reproducing

```powershell
cd backend; .\.venv\Scripts\Activate.ps1
python -m benchmarks.runner              # normalization, all candidates
python -m benchmarks.qa_runner           # Module 4-style Q&A, all candidates
python -m benchmarks.runner --recompute  # rescore stored runs without calling a model
```

Tags must match `ollama list` exactly. The first attempt at this benchmark asked
for `martain7r/finance-llama-8b` where the installed tag was
`martain7r/finance-llama-8b:q4_k_m`; every request 404'd and the run produced a
complete-looking result file in which nothing had been measured — and scored it
100% on abstention, because a model that never answers never answers wrongly.
The runner now refuses an uninstalled tag, and an unanswered case can no longer
count as a correct abstention.
