# BalanceSheet

**A Multi-Agent AI Framework for Automated Balance Sheet Review**

Upload a Balance Sheet (PDF or Excel); the system validates it, extracts Assets, Liabilities and Shareholders' Equity, verifies the accounting equation

```
Total Assets = Total Liabilities + Shareholders' Equity
```

and stores the result in MongoDB. Later modules normalize terminology, compute financial ratios in deterministic Python, and explain the results through an LLM with RAG.

> **Scope:** Balance Sheet only, single reporting period. Income Statement, Cash Flow, forecasting, benchmarking and anomaly detection are future scope.

## Status

This repository currently contains the **project foundation**. Built and working:

- FastAPI backend with MongoDB Atlas connectivity (PyMongo `AsyncMongoClient`, Stable API v1)
- The full Module 1 data model (`Decimal`-based, stored as `Decimal128`)
- Local file storage behind a replaceable `FileStorage` abstraction
- **The accounting-equation validator**, with unit tests
- React + TypeScript frontend with a backend-connectivity check

Not yet implemented: PDF/Excel parsing, OCR, Balance Sheet identification, and Modules 2–4. Their entry points exist with documented signatures and raise `NotImplementedError` / `StageNotImplemented`.

## Modules

| Module | Package | Responsibility | State |
|---|---|---|---|
| 1 | `ingestion` | Upload & Validation — parsing, OCR, identification, equation check | Equation check done; parsing pending |
| 2 | `extraction` | Full Data Extraction & Normalization | Not implemented |
| 3 | `ratios` | Deterministic Financial Ratio Engine | Not implemented |
| 4 | `insights` | LLM + RAG | Not implemented |

## Stack

React + Vite + TypeScript · Python + FastAPI · MongoDB Atlas · pytest / Vitest

## Setup

Requires Python 3.11+, Node 18+, and a MongoDB Atlas cluster.

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

The suite splits into **unit tests**, which need nothing external, and **integration tests**, which need a reachable MongoDB cluster. Integration tests are exactly those using the `test_db` fixture; the `integration` marker is applied to them automatically, so there is no decorator to forget.

They run against a separate `<MONGODB_DB>_test` database which is dropped afterwards — a test run never touches real data.

```powershell
cd backend; .\.venv\Scripts\Activate.ps1

pytest                                   # everything (integration skips if Atlas is down)
pytest -m "not integration"              # unit tests only — no cluster needed
pytest -m integration --require-mongo    # integration only — unreachable Atlas FAILS
```

`--require-mongo` turns the default skip into a hard failure. Use it in CI and whenever you are deliberately verifying Atlas connectivity: there, a connection failure quietly reported as "skipped" is a false green.

## Notes

- Commands are PowerShell; chain with `;` rather than `&&`.
- OCR (when implemented) requires the **Tesseract system binary**, not just a pip package.
- See [CLAUDE.md](CLAUDE.md) for architecture constraints and module boundaries.
