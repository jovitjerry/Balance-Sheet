# BalanceSheet

**A Multi-Agent AI Framework for Automated Balance Sheet Review**

Upload a Balance Sheet (PDF or Excel); the system validates it, extracts Assets, Liabilities and Shareholders' Equity, verifies the accounting equation

```
Total Assets = Total Liabilities + Shareholders' Equity
```

and stores the result in MongoDB. Later modules normalize terminology, compute financial ratios in deterministic Python, and explain the results through an LLM with RAG.

> **Scope:** Balance Sheet only, single reporting period. Income Statement, Cash Flow, forecasting, benchmarking and anomaly detection are future scope.

## Status

Built and working:

- FastAPI backend with MongoDB Atlas connectivity (PyMongo `AsyncMongoClient`, Stable API v1)
- The full data model (`Decimal`-based, stored as `Decimal128`)
- Local file storage behind a replaceable `FileStorage` abstraction
- **Upload → validation → extraction → normalization → ratios** in one request
- **The accounting-equation validator** and **the ratio engine**, both deterministic Python
- React + TypeScript frontend with a backend-connectivity check

**Modules 1, 2 and 3 are complete.** Module 4 is not started; its entry point exists with a documented signature and raises `StageNotImplemented`.

## Modules

| Module | Package | Responsibility | State |
|---|---|---|---|
| 1 | `ingestion` | Upload & Validation — parsing, OCR, identification, equation check | **Implemented** |
| 2 | `extraction` | Full Data Extraction & Normalization | **Implemented** |
| 3 | `ratios` | Deterministic Financial Ratio Engine | **Implemented** |
| 4 | `insights` | LLM + RAG | Not implemented |

### What Module 1 does

`POST /api/v1/documents` takes a PDF or `.xlsx` and runs it through:

file validation → content validation (magic bytes must agree with the extension) → PDF/Excel parsing → per-page scanned detection → OCR where needed → preliminary extraction → current-period selection → Balance Sheet identification → locating Total Assets / Liabilities / Equity → the accounting-equation check → persistence.

Rejections are recorded rather than discarded, and the response distinguishes two cases: a document that is **not a Balance Sheet** is a `422`, while a Balance Sheet that **fails validation** is a `201` whose `status` is `rejected` and whose `validation` and `equation_check` say exactly what failed.

### What Module 2 does

A document that passes Module 1 continues straight into Module 2, and the
stored `status` becomes `extracted`. It runs in two clearly separated halves.

**Extraction - deterministic, no model involved.** Every line item is read from
the document: its label exactly as printed, the figure exactly as printed
beside the parsed `Decimal`, the section and (where the sheet says) the
current/non-current subsection, and a `SourceRef` back to the page, row and
column. Only the reporting period Module 1 selected is ever read. Totals and
subtotals are excluded - they summarise the lines rather than being any - and a
line whose figure will not parse is kept with `status: unparsed_value` rather
than silently dropped.

**Normalization - a local model, tightly fenced.** Each label is mapped onto a
small, versioned canonical vocabulary (`taxonomy.py`, 22 categories sized by
what Module 3's ratios will need). Three routes, and every mapping records
which one decided it: the identity dictionary for a document that already
prints the canonical wording, a cache for repeats, and the model for everything
else - which is every real synonym, *Trade Debtors*, *Stock-in-Trade*,
*Creditors*, *Shareholders' Funds*.

The model never sees a figure and never produces one. It is given a label, its
section, its neighbours and the permitted vocabulary, and answers with a
category from that list. The vocabulary is sent as a JSON Schema `enum`, which
Ollama compiles into a decoding grammar - so an invented category is
structurally unreachable, not merely discouraged. Python re-validates anyway,
and rejects a malformed answer, a label outside the taxonomy, a label that
contradicts the section it was printed in, and a confidence below the floor.

**A rejected answer never becomes a guess.** Every one of those lands on
`needs_review` with the line item completely intact - which Module 3 can see
and skip. A confidently wrong category is one it could not.

### What Module 3 does

The document continues into the ratio engine and the stored `status` becomes
`analyzed`. Seven Balance-Sheet-only ratios are computed in **pure, synchronous
Python**: current, quick, cash, debt-to-equity, debt, equity, and working
capital. No language model is involved, and none can be - the module imports no
path to one, and a test reads the imports to prove it.

That constraint is not decoration. Module 2's own Q&A benchmark had three of
four candidate models make arithmetic errors on a Balance Sheet containing
fifteen numbers; one summed current assets as 550,000 instead of 850,000 and
concluded the company could not pay its short-term bills, the exact opposite of
the truth.

**Provenance is the hard part, not the arithmetic.** A Balance Sheet holds
figures at three levels - leaf line items, printed subtotals, section grand
totals - and a ratio that mixes levels is wrong in a way that still looks
plausible. One rule settles it:

> Prefer what the document printed and Module 1 validated. Derive only what was
> not printed.

So the three grand totals are Module 1's, read off the page and checked against
the accounting equation. Current and non-current subtotals have to be summed
from line items, because Module 2 excludes every printed subtotal and the figure
does not exist in the data. Each result records which basis each of its sides
used, so the mixed authority is disclosed rather than hidden.

That same exclusion makes summing safe: `line_items` holds leaves and only
leaves, and the grand totals live in a different field, so nothing summable
contains anything else summable. Double counting is structurally impossible -
and the engine re-applies Module 2's own total-line predicate as a guard anyway,
so a regression there fails loudly instead of quietly doubling a section.

**Nothing is fabricated.** A ratio whose inputs are absent, or whose denominator
is zero, is `unavailable` with a machine-readable reason - not infinity, not a
bare `null`. A ratio computed from an incomplete set of line items is `partial`,
naming the lines it left out and their total, so a reader can bound the true
value rather than guess at it. **Nothing is clamped, either:** negative equity
and negative working capital keep their signs and carry a warning, because
hiding insolvency would be the worst thing this system could do.

Every figure is walkable back to ink on the page - canonical label → the label
as printed → the figure as printed → page, row and column. Money is `Decimal`
throughout; sums are exact, a quotient is rounded once at six decimal places,
and working capital is never rounded at all.

The formulas, the fields each one draws on, and the limitations of each are
generated into [`backend/docs/RATIOS.md`](backend/docs/RATIOS.md) from the
declarations themselves, so the report and the code cannot disagree. Where a
ratio has competing accounting definitions - the quick ratio does - the choice
and the rejected alternative are both written down.

## Stack

React + Vite + TypeScript · Python + FastAPI · MongoDB Atlas · pytest / Vitest

Module 1 parsing: **pdfplumber** (digital PDF text and tables) · **pypdfium2** (rasterisation) · **Tesseract** via pytesseract (OCR) · **openpyxl** (`.xlsx`)

Module 2 normalization: a **local** model through **Ollama**, reached over HTTP behind a provider interface. No paid API, and no data leaves the machine.

## Setup

Requires Python 3.11+, Node 18+, a MongoDB Atlas cluster, and — for scanned
documents — the **Tesseract system binary**.

> **OCR needs Tesseract installed as a program, not just `pip install pytesseract`.**
> On Windows: `winget install UB-Mannheim.TesseractOCR`, then confirm with
> `tesseract --version`. Without it the API still runs and still handles every
> document that has a text layer; a *scanned* page is refused with a `503`
> rather than being silently read as blank.

> **Terminology normalization needs Ollama, also a separate program.**
> Install it from [ollama.com](https://ollama.com), then pull a model:
> `ollama pull qwen3:8b`. Without it the API still runs and still extracts
> every line item, figure and source reference; labels that are not already
> the canonical wording are recorded as `needs_review` rather than guessed
> at. Set `LLM_REQUIRED=true` to refuse instead of degrading.

Only `.pdf` and `.xlsx` are accepted. The legacy binary `.xls` format is out of scope.

**1. Configure environment**

```powershell
Copy-Item .env.example .env
```

Fill in `MONGODB_URI` and the remaining keys. `.env` is gitignored and must never be committed.

**2. Backend**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload
```

Runs on http://localhost:8000 — check http://localhost:8000/api/v1/health.

**3. Frontend**

```powershell
cd frontend
npm install
npm run dev
```

Runs on http://localhost:5173 and proxies `/api` to the backend.

## Tests

The suite splits three ways by what a test needs from outside the process:

| Kind | Needs | Marked by |
|---|---|---|
| **unit** | nothing | — |
| **integration** | a reachable MongoDB cluster | using the `test_db` fixture |
| **ocr** | the Tesseract system binary | using the `ocr_engine` fixture |
| **llm** | Ollama running with the model pulled | using the `ollama_provider` fixture |
| **benchmark** | Ollama and the candidate models | an explicit `@pytest.mark.benchmark` |

Markers are applied automatically from fixture usage, so there is no decorator to forget. Integration tests run against a separate `<MONGODB_DB>_test` database which is dropped afterwards — a test run never touches real data.

```powershell
cd backend; .\.venv\Scripts\Activate.ps1

pytest                                              # everything; unavailable dependencies skip
pytest -m "not integration and not ocr and not llm" # pure unit tests — nothing external
pytest -m integration --require-mongo               # integration only — unreachable Atlas FAILS
pytest -m ocr --require-ocr                         # OCR only — missing Tesseract FAILS
pytest -m "llm and not benchmark" --require-ollama  # the live Ollama round trip
pytest -m benchmark --require-ollama                # the model comparison — slow, opt-in
```

`--require-mongo`, `--require-ocr` and `--require-ollama` turn the default skip into a hard failure. Use them in CI and whenever you are deliberately verifying that dependency: there, a missing binary or a failed connection quietly reported as "skipped" is a false green.

Almost nothing needs a live model. The whole normalization ladder — every
validation rule and every failure mode — is exercised against a stub
provider, because a real model gives no reliable way to produce a malformed
answer on demand. What the `llm` tests cover is the transport.

**Module 3 needs nothing at all.** Its acceptance tests run the entire chain —
parse, identify, select the period, locate the totals, extract every line item,
normalize the terminology, compute the ratios — against the real Meridian and
ABC fixtures with the model switched off, using a provider that raises if it is
ever called. Every label on those documents already spells its canonical
concept, so the identity dictionary resolves all of them. The expected values
are hand-derived from the printed figures, and the derived subtotals must land
on exactly the subtotals the document itself prints and Module 2 discards.

## Choosing the model

`OLLAMA_MODEL` is meant to be settled by measurement, not by reputation.

```powershell
ollama pull qwen3:8b; ollama pull qwen3:4b; ollama pull llama3.1:8b
ollama pull martain7r/finance-llama-8b

cd backend; .\.venv\Scripts\Activate.ps1; python -m benchmarks.runner
```

75 labelled cases — canonical wordings, synonyms, abbreviations, unusual
phrasings, genuinely ambiguous labels and nonsense — go to each candidate,
and `benchmarks/results/comparison.md` gets the table.

**Accuracy and abstention are scored separately, on purpose.** A model that
never says "I don't know" scores well on the easy cases and is dangerous in
production, because on the ambiguous ones it produces a confident wrong
category that nothing downstream can detect. `finance-llama-8b` is included
as a hypothesis to test rather than a favourite: it is tuned for financial QA
and sentiment, not label-to-taxonomy mapping, and domain fine-tunes often
lose the instruction-following of the base model they came from.
`benchmarks/qa_cases.json` scores the same models on Module 4-style questions
separately, so a good classifier that is a poor explainer is visible as such.

### Result

**`qwen3:8b` is the selected model for Module 2**, decided 2026-08-26 from the
measurements below. The full record, including the limitations of the
evidence, is in [`benchmarks/results/MODEL_SELECTION.md`](backend/benchmarks/results/MODEL_SELECTION.md).

| Model | Accuracy | Correct abstention | Over-answered | Cold | Warm mean | VRAM (MB) |
|---|---|---|---|---|---|---|
| **qwen3:8b** | **97%** | 54% | 46% | 80.9s | **4.15s** | 6460 |
| qwen3:4b | 95% | **62%** | **38%** | 15.7s | 4.68s | **4160** |
| llama3.1:8b | 95% | 46% | 54% | 18.1s | 4.39s | 6156 |
| finance-llama-8b:q4_k_m | 95% | **15%** | **85%** | 11.5s | 4.85s | 5141 |

It won on accuracy, output cleanliness and steady-state latency. The
finance-tuned candidate did not beat it and was the worst on abstention by a
wide margin — it answered every ambiguous label and three of five nonsense
ones, mapping `Schedule 14` to `cash_and_cash_equivalents`. Domain tuning on
financial text did not help with label-to-taxonomy mapping.

Two things the record keeps honest: the accuracy lead is a **single case**
(60/62 vs 59/62, one run), and this model has the **slowest cold start** at
80.9s. `qwen3:4b` is the obvious alternative if headroom or first-request
latency matters more than the last point of accuracy.

**This does not settle Module 4.** That module will drive the same provider
with different prompts and must be evaluated on its own evidence; the Q&A
benchmark does not support this model for explanation work. `OLLAMA_MODEL`
stays a setting behind the `LlmProvider` seam so the two choices stay separate.

## Notes

- Commands are PowerShell; chain with `;` rather than `&&`.
- OCR requires the **Tesseract system binary**; normalization requires **Ollama** with a model pulled. Neither is a pip package.
- See [CLAUDE.md](CLAUDE.md) for architecture constraints and module boundaries.
