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
| 1 | `ingestion` | Upload & Validation — file validation, preliminary PDF/Excel parsing, OCR when required, Balance Sheet identification, required-field and accounting-equation validation |
| 2 | `extraction` | Full Data Extraction & Normalization |
| 3 | `ratios` | Deterministic Financial Ratio Engine |
| 4 | `insights` | LLM + RAG explanation and chat |

### Module boundaries

- Module 1 performs **only enough** extraction to establish document readability, Balance Sheet identity, the three section totals, required fields, and the accounting equation. It holds **no general terminology dictionary**.
- Module 2 owns **complete line-item extraction and all normalization**. Do not duplicate normalization logic into Module 1; Module 1's total-line locator delegates to Module 2's vocabulary once that exists.
- Keep these boundaries clear. A change that blurs them needs to be raised, not absorbed.

## Implementation constraints

- **Financial calculations must never be delegated to the LLM.** The accounting equation and all ratios are deterministic Python. The LLM explains figures it is handed; it never produces or recomputes them. `compute_ratios` is deliberately synchronous and pure — no DB handle, no LLM client, no I/O.
- **Money is `Decimal`, never `float`** — float drift at the cent level would fail Balance Sheets that genuinely balance. Values are stored in MongoDB as `Decimal128`, and the `Decimal` ↔ `Decimal128` conversion is performed by **`core/money.py` at the schema/storage boundary** (`encode_for_mongo` / `decode_from_mongo`, reached via `BalanceSheetDocument.to_mongo()` / `.from_mongo()`). MongoDB codec options do **not** perform this conversion: `CODEC_OPTIONS` in `core/db.py` sets only `tz_aware`. Go through `to_mongo()` / `from_mongo()` rather than converting ad hoc.
- **MongoDB access is PyMongo `AsyncMongoClient` with Stable API v1. Never Motor** — Motor is deprecated in favour of the PyMongo async API.
- The client is created and closed in the FastAPI **lifespan** handler and reached through the `get_db()` dependency. Creating it at import time breaks the event loop under pytest.
- **Original uploaded files go to the `FileStorage` abstraction (`core/storage.py`), never inline in a MongoDB document.**
- Raw parser output is preserved in `PreliminaryExtraction` with source page metadata, separately from the structured `ExtractedBalanceSheet`. Raw table cells stay **strings** — `"(2,300)"` and `"1,234.5"` must remain recoverable as printed.
- **Unimplemented pipeline stages raise `StageNotImplemented`** — never a silent success, and never a fabricated result.

## Security

- **Never hard-code secrets.** All configuration comes from `.env` via `core/config.py`.
- **`.env` must remain gitignored.** Never commit it, copy its values into another file, echo it into logs, or print it in output.
- `.env.example` documents every key and contains **no secrets**. Only `MONGODB_URI` is left blank to be filled in; optional keys are commented out beside their defaults, because an uncommented key with an empty value is a validation error rather than "use the default".
- Storage keys derive from the file's SHA-256, **never from the client-supplied filename** — uploaded filenames are attacker-controlled and are the classic path-traversal vector.

## Development

Windows + PowerShell. Chain commands with `;`, not `&&`.

```powershell
# Backend
cd backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload   # http://localhost:8000

# Tests
pytest                                   # everything; integration skips if Atlas is down
pytest -m "not integration"              # unit tests only - no cluster needed
pytest -m integration --require-mongo    # integration only; unreachable Atlas FAILS

# Frontend
cd frontend; npm run dev                                                  # http://localhost:5173
```

- Tests needing a live cluster are those using the `test_db` fixture; the `integration` marker is applied automatically from fixture usage, so never hand-apply it. They run against `<MONGODB_DB>_test`, which is dropped on teardown.
- Use `--require-mongo` in CI and when verifying Atlas: a connection failure reported as "skipped" is a false green.
- New logic is written **test-first**.
- Git is **local only** for now — no remote, no push. GitHub is configured later by the maintainer.

## Setup gotcha

OCR requires the **Tesseract system binary**, not just a pip package. Installing `pytesseract` alone will not work.
