# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**A Multi-Agent AI Framework for Automated Balance Sheet Review** — an academic mini-project.

A user uploads a Balance Sheet (PDF or Excel). The system validates the file, parses it (OCR when scanned), extracts Assets / Liabilities / Shareholders' Equity, validates the accounting equation, and stores the result in MongoDB. Later stages normalize terminology, compute financial ratios, and explain results via an LLM with RAG.

## Scope — hard limits

- **Balance Sheet only.** No Income Statement. No Cash Flow Statement.
- **Single reporting period only.** No multi-year or year-over-year comparison. If an uploaded sheet is comparative, only one period is analyzed.
- **Not in scope:** forecasting, benchmarking, anomaly detection, authentication.
- **Do not implement future scope unless explicitly requested.** When a task appears to need out-of-scope work, say so and stop — do not scaffold for it "just in case".

## Architecture — four modules

Each module is a self-contained package under `backend/app/modules/`, exposing one documented entry point. `backend/app/core/pipeline.py` chains them.

| Module | Package | Responsibility |
|---|---|---|
| 1 | `ingestion` | Upload & Validation — file validation, preliminary PDF/Excel parsing, OCR when required, Balance Sheet identification, required-field and accounting-equation validation. **Implemented.** |
| 2 | `extraction` | Full Data Extraction & Normalization — complete line-item extraction, section/subsection structure, and terminology mapping onto a versioned canonical vocabulary using a local LLM through Ollama. **Implemented.** |
| 3 | `ratios` | Deterministic Financial Ratio Engine — seven Balance-Sheet-only ratios computed in pure Python, with full provenance. **Implemented.** |
| 4 | `insights` | LLM + RAG explanation and chat |

### Module boundaries

- Module 1 performs **only enough** extraction to establish document readability, Balance Sheet identity, the three section totals, required fields, and the accounting equation. It holds **no general terminology dictionary**.
- Module 2 owns **complete line-item extraction and all normalization**. Its vocabulary lives in `extraction/taxonomy.py` and nowhere else. Do not duplicate it into Module 1.
- Keep these boundaries clear. A change that blurs them needs to be raised, not absorbed.
- The narrow phrase set Module 1 *is* allowed to know lives in `ingestion/anchors.py`: document titles, the three section headers, the three total lines. Nothing else. A line-item synonym appearing there means the boundary has been crossed — `tests/test_pipeline.py::TestModuleBoundaries` enforces this.
- Module 1 records currency and scale (`UnitHint`) but **never applies them**. A sheet printed "in thousands" is stored with its figures exactly as printed. Scaling is normalization, and normalization is Module 2's.

### The shared layer

`core/` holds what **both** modules read, and depends on no module. That is
what makes it shareable, and `tests/test_pipeline.py::TestModuleBoundaries`
enforces it.

| `core/` module | Why it is shared, not owned |
|---|---|
| `lines.py` | The line/segment view of a document, plus `figure_for` — the selected-period column choice. **One implementation, deliberately.** Module 1 picks its totals with it and Module 2 picks every line item with it; two implementations could disagree and Module 2 would silently extract the comparative column Module 1 rejected, on a document where both columns hold entirely plausible numbers. |
| `amounts.py` | Reading a printed figure as a `Decimal`. A value parse, not terminology. |
| `text.py` | Label shape only — case, punctuation, `+`/`&` → `and`. Module 1 matches anchors with it; Module 2 keys its identity dictionary and its cache with it, and those two must agree. |
| `llm/` | The `LlmProvider` seam. Module 4 will drive the same local model with different prompts. |

Exactly two files in `core/` may name a module, because their job is
composition rather than sharing: `deps.py` (hands the assembled application's
parts to a request) and `pipeline.py` (the orchestration boundary — an
orchestrator that may not name what it orchestrates is not one).

## Module 2 constraints

- **Extraction and normalization are separate, in that order.** Extraction
  answers "what did the document say?" and completes before any model is
  consulted, so a document is fully extracted with Ollama switched off and a
  normalization failure can never touch a figure.
- **The LLM maps terminology and nothing else.** It is never shown a figure,
  never asked to compute, and never allowed to alter a value, a currency or a
  unit scale. The accounting equation stays in Module 1.
- **The canonical vocabulary is closed and versioned.** It is handed to the
  model as a JSON Schema `enum`, which Ollama compiles into a decoding grammar,
  so an invented category is structurally unreachable. Python re-validates
  anyway — a grammar cannot prevent a truncated response, and the
  section-fit check is one no grammar could express.
- **A rejected answer never becomes a guess.** Malformed JSON, a label outside
  the taxonomy, a label contradicting its printed section, a confidence below
  the floor, an unreachable model — every one lands on `needs_review` with
  the line item intact. `needs_review` is a real answer; `other_*` is not its
  synonym (that means the *document* printed a residual line).
- **`confidence` is the model's own opinion, not a calibrated probability.** It
  may demote a mapping to review. It may never rescue one that failed a check.
- **The original label is never overwritten.** `label` is what was printed;
  `normalization.canonical_label` sits beside it. "Trade Debtors" and "Trade
  Receivables" stay distinguishable while mapping to one concept.
- **The identity dictionary is identity only** — derived from the taxonomy,
  never hand-written. Every genuine synonym goes to the model; a broad alias
  table would make the model decorative and the benchmark meaningless.
- **Ollama unreachable degrades, it does not fail.** Unresolved labels become
  `needs_review`/`unavailable` and the extraction still stands. `LLM_REQUIRED=true`
  turns that into a 503 for CI and demos.
- **`temperature=0`, and the deciding model and taxonomy version are stored on
  every mapping** — an academic result that moves between runs is not a result.
- **The model is chosen by measurement.** `backend/benchmarks/` scores
  candidates on 75 cases, with abstention scored *separately* from accuracy: a
  model that never declines scores well on the easy cases and is dangerous on
  the ambiguous ones. Do not change `OLLAMA_MODEL` on reputation.
- **Selected model: `qwen3:8b`** (2026-08-26) — 97% accuracy, clean
  schema-constrained output, 4.15s warm per label, 6.4 GB on an 8 GB card. The
  finance-tuned candidate did not beat it and answered every ambiguous label.
  Record, evidence and limitations:
  `backend/benchmarks/results/MODEL_SELECTION.md`. Re-run the benchmark before
  changing it; the accuracy lead is one case and the cold start is the slowest
  of the four.
- **This does not settle Module 4.** It will drive the same `LlmProvider` with
  its own prompts and must select its own model on its own evidence — the
  Q&A benchmark does **not** support `qwen3:8b` for explanation work. Keep
  `OLLAMA_MODEL` a setting; do not hard-code a model anywhere.

## Module 3 constraints

- **Seven ratios, Balance Sheet only:** current, quick, cash, debt-to-equity,
  debt, equity, working capital. Anything needing an Income Statement or Cash
  Flow Statement is out of scope and `test_definitions.py` enforces it.
- **Zero dependency on a language model, structurally.** `tests/test_pipeline.py::TestModule3IsDeterministic`
  reads the imports and fails if anything under `modules/ratios/` reaches
  `app.core.llm`, `httpx`, `ollama`, `pymongo`, `app.core.db`, `app.core.storage`
  or `pathlib`. `compute_ratios` is synchronous and takes no dependency
  parameters. The whole module is testable with nothing installed.
- **Provenance is the design.** *Prefer what the document printed and Module 1
  validated; derive only what was not printed.* The three grand totals come from
  `section.total`; current/non-current subtotals are summed from normalized
  leaves, because Module 2 discards the printed subtotals. Every result records
  `numerator_basis` / `denominator_basis`, so the mixed authority is disclosed
  rather than hidden.
- **Classification is the canonical category, never the printed heading.**
  `LineItem.subsection` is evidence, not authority — many sheets print no
  current/non-current headings at all. The heading may only *narrow* which
  quantities an **unclassified** line could have belonged to; it never places a
  figure into a sum.
- **Double counting is structurally impossible** — `line_items` is leaf-only
  (Module 2's `is_total_line` excluded every total) and grand totals live in a
  different field. `aggregation._guard` re-applies Module 2's own predicate so a
  regression there fails loudly here instead of inflating a section silently.
- **Duplicate canonical labels are summed and flagged, never de-duplicated.**
  Two printed lines are two figures with two source references.
- **Nothing is fabricated.** Missing inputs or a zero denominator →
  `unavailable` with a machine-readable reason from a closed set. Incomplete
  inputs → `partial`, naming the excluded lines and their total so a reader can
  bound the true value. `needs_review` is never guessed at, never zeroed, and
  never mapped to `other_*`.
- **Nothing is clamped.** Negative equity, negative working capital and contra
  balances keep their signs and carry a warning. Hiding insolvency would be the
  worst thing this system could do.
- **Precision:** exact sums, one division, one final quantize to 6 dp
  ROUND_HALF_UP. Working capital is money and is never rounded. Unrounded
  numerator and denominator are stored so any consumer can re-derive.
  `RATIO_DECIMAL_PLACES` is a module constant, **not** a setting — a deployment
  able to change it could change a published result without a version bump.
- **`RATIO_SPEC_VERSION` is separate from `TAXONOMY_VERSION`** — a formula change
  and a vocabulary change are different events.
- **Quick ratio is the SUBTRACTIVE definition** — `(CA − Inventory − Prepaid) / CL`.
  Chosen so it shares the current ratio's numerator basis and `Quick ≤ Current`
  always holds. Where a ratio has competing definitions the choice and the
  rejected alternative are both written into `definitions.py`.
- **`docs/RATIOS.md` is generated** from `definitions.py` by
  `python -m scripts.generate_ratio_docs`; `test_docs.py` fails if it drifts.
  Do not edit it by hand.

## Implementation constraints

- **Financial calculations must never be delegated to the LLM.** The accounting equation and all ratios are deterministic Python. The LLM explains figures it is handed; it never produces or recomputes them. `compute_ratios` is deliberately synchronous and pure — no DB handle, no LLM client, no I/O.
- **Money is `Decimal`, never `float`** — float drift at the cent level would fail Balance Sheets that genuinely balance. Values are stored in MongoDB as `Decimal128`, and the `Decimal` ↔ `Decimal128` conversion is performed by **`core/money.py` at the schema/storage boundary** (`encode_for_mongo` / `decode_from_mongo`, reached via `BalanceSheetDocument.to_mongo()` / `.from_mongo()`). MongoDB codec options do **not** perform this conversion: `CODEC_OPTIONS` in `core/db.py` sets only `tz_aware`. Go through `to_mongo()` / `from_mongo()` rather than converting ad hoc.
- **MongoDB access is PyMongo `AsyncMongoClient` with Stable API v1. Never Motor** — Motor is deprecated in favour of the PyMongo async API.
- The client is created and closed in the FastAPI **lifespan** handler and reached through the `get_db()` dependency. Creating it at import time breaks the event loop under pytest.
- **Original uploaded files go to the `FileStorage` abstraction (`core/storage.py`), never inline in a MongoDB document.**
- Raw parser output is preserved in `PreliminaryExtraction` with source page metadata, separately from the structured `ExtractedBalanceSheet`. Raw table cells stay **strings** — `"(2,300)"` and `"1,234.5"` must remain recoverable as printed.
- **Module 2 computes no ratio.** It produces the structured data Module 3 consumes and stops there.
- **Module 3 computes no explanation.** It produces figures and the evidence behind them; interpreting them is Module 4's, and Module 4 must select its own model on its own evidence.
- **Unimplemented pipeline stages raise `StageNotImplemented`** — never a silent success, and never a fabricated result. The same rule governs a missing capability: a scanned page with no OCR engine raises `OcrUnavailable` rather than yielding an empty page, because an empty page would go on to be reported as "not a Balance Sheet" — a verdict the system never actually reached.
- **Module 1 parsing stack is fixed:** pdfplumber (digital PDF text/tables), pypdfium2 (rasterisation), Tesseract via pytesseract behind the `OcrEngine` protocol, openpyxl (`.xlsx` only — `.xls` is out of scope). PyMuPDF was rejected on AGPL-3.0 licensing.
- **Word positions are kept for every PDF page, digital and scanned alike** (`SourcePage.words`). A Balance Sheet's figure sits far right of its label, and on a comparative sheet the *column* is what identifies the reporting period — that lives only in the geometry. Flat reading order loses it.
- **Rejection semantics are hybrid.** Not a Balance Sheet (unreadable, or a different statement) → raise, and the router answers 4xx. A Balance Sheet that fails validation (missing total, or does not balance) → return normally with the evidence; the router answers 201 and `status` is `rejected`. Either way the record is **kept** — a rejected submission is audit evidence, not rubbish.
- **`encode_for_mongo` is the storage encoding boundary.** BSON has no date-without-time type, so a bare `date` is stored as an ISO string there. `datetime` is checked first, since `datetime` is a subclass of `date`.

## Security

- **Never hard-code secrets.** All configuration comes from `.env` via `core/config.py`.
- **`.env` must remain gitignored.** Never commit it, copy its values into another file, echo it into logs, or print it in output.
- `.env.example` documents every key and contains **no secrets**. Only `MONGODB_URI` is left blank to be filled in; optional keys are commented out beside their defaults, because an uncommented key with an empty value is a validation error rather than "use the default".
- Storage keys derive from the file's SHA-256, **never from the client-supplied filename** — uploaded filenames are attacker-controlled and are the classic path-traversal vector.
- `MONGODB_URI` is a pydantic `SecretStr`. An Atlas SRV URI embeds the database password, and a plain `str` prints in full wherever a `Settings` object is repr'd — pytest's local-variable dump on a failure being the one that bites. Unwrap it with `.get_secret_value()` only in `create_client`.
- **Uploads are validated by content, not by extension**, and the size cap is enforced *while streaming*. Buffering first and measuring afterwards would make `MAX_UPLOAD_BYTES` a memory-exhaustion vector rather than a defence against one.
- **API responses expose no internals** — no stack traces, filesystem paths, library names, or connection strings. Every caller-visible error message is one this codebase wrote deliberately; parser exceptions are logged and replaced, never forwarded. `tests/modules/ingestion/test_router.py::TestResponsesLeakNothing` enforces this.

## Development

Windows + PowerShell. Chain commands with `;`, not `&&`.

```powershell
# Backend
cd backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload   # http://localhost:8000
cd backend; .\.venv\Scripts\Activate.ps1; pytest

# Test modes. Markers are applied automatically from fixture usage:
#   test_db -> integration, ocr_engine -> ocr
pytest -m "not integration and not ocr"   # pure unit tests, nothing external
pytest -m integration --require-mongo     # unreachable Atlas FAILS instead of skipping
pytest -m ocr --require-ocr               # missing Tesseract FAILS instead of skipping

# Frontend
cd frontend; npm run dev                                                  # http://localhost:5173
```

- New logic is written **test-first**.
- Git is **local only** for now — no remote, no push. GitHub is configured later by the maintainer.

## Setup gotcha

OCR requires the **Tesseract system binary**, not just a pip package. Installing `pytesseract` alone will not work.

Normalization requires **Ollama** installed as a program with a model pulled
(`ollama pull qwen3:8b`). The pip side talks to it over HTTP and cannot supply
it. Without it the API still runs and still extracts every line item; labels
that are not already canonical are marked `needs_review`.
