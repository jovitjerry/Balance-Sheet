# BalanceSheet

**A Multi-Agent AI Framework for Automated Balance Sheet Review**

Upload a Balance Sheet (PDF or Excel); the system validates it, extracts Assets, Liabilities and Shareholders' Equity, verifies the accounting equation

```
Total Assets = Total Liabilities + Shareholders' Equity
```

and stores the result in MongoDB. It then normalizes terminology with a local LLM, computes financial ratios in deterministic Python, and answers questions about the document through grounded retrieval-augmented generation.

> **Scope:** Balance Sheet only, single reporting period. Income Statement, Cash Flow, forecasting, benchmarking and anomaly detection are future scope.

## Status

Built and working:

- FastAPI backend with MongoDB Atlas connectivity (PyMongo `AsyncMongoClient`, Stable API v1)
- The full data model (`Decimal`-based, stored as `Decimal128`)
- Local file storage behind a replaceable `FileStorage` abstraction
- **Upload → validation → extraction → normalization → ratios** in one request
- **Ask questions** about a processed document and get grounded, cited answers
- **The accounting-equation validator** and **the ratio engine**, both deterministic Python
- React + TypeScript frontend with a backend-connectivity check

All four modules are complete. Modules 1–3 run on upload; Module 4 answers questions on request.

## Modules

| Module | Package | Responsibility | State |
|---|---|---|---|
| 1 | `ingestion` | Upload & Validation — parsing, OCR, identification, equation check | **Implemented** |
| 2 | `extraction` | Full Data Extraction & Normalization | **Implemented** |
| 3 | `ratios` | Deterministic Financial Ratio Engine | **Implemented** |
| 4 | `insights` | Grounded Q&A over a processed document | **Implemented** (request-driven) |

### What Module 1 does

`POST /api/v1/documents` takes a PDF or `.xlsx` and runs it through:

file validation → content validation → PDF/Excel parsing → per-page scanned detection → OCR where needed → preliminary extraction → current-period selection → Balance Sheet identification → locating Total Assets / Liabilities / Equity → the accounting-equation check → persistence.

Rejections are recorded rather than discarded, and the response distinguishes two cases: a document that is **not a Balance Sheet** is a `422`, while a Balance Sheet that **fails validation** is a `201` whose `status` is `rejected` and whose `validation` and `equation_check` say exactly what failed.

### What Module 2 does

A document that passes Module 1 continues straight into Module 2, and the stored `status` becomes `extracted`. It runs in two clearly separated halves.

**Extraction - deterministic, no model involved.** Every line item is read from the document: its label exactly as printed, the figure exactly as printed beside the parsed `Decimal`, the section and (where the sheet says) the current/non-current subsection, and a `SourceRef` back to the page, row and column. Only the reporting period Module 1 selected is ever read. Totals and subtotals are excluded — they summarise the lines rather than being one — and a line whose figure will not parse is kept with `status: unparsed_value` rather than silently dropped.

**Normalization - a local model, tightly fenced.** Each label is mapped onto a small, versioned canonical vocabulary (`backend/app/modules/extraction/taxonomy.py`, 22 categories sized by what Module 3's ratios will need). Three routes, and every mapping records which one decided it: the identity dictionary for a document that already prints the canonical wording, a cache for repeats, and the model for everything else — which is every real synonym, *Trade Debtors*, *Stock-in-Trade*, *Creditors*, *Shareholders' Funds*.

The model never sees a figure and never produces one. It is given a label, its section, its neighbours and the permitted vocabulary, and answers with a category from that list. The vocabulary is sent as a JSON Schema `enum`, which Ollama compiles into a decoding grammar — so an invented category is structurally unreachable, not merely discouraged. Python re-validates anyway, and rejects a malformed answer, a label outside the taxonomy, a label that contradicts the section it was printed in, and a confidence below the floor.

**A rejected answer never becomes a guess.** Every one of those lands on `needs_review` with the line item completely intact — which Module 3 can see and skip. A confidently wrong category is one it could not.

### What Module 3 does

The document continues into the ratio engine and the stored `status` becomes `analyzed`. Seven Balance-Sheet-only ratios are computed in **pure, synchronous Python**: current, quick, cash, debt-to-equity, debt, equity, and working capital. No language model is involved, and none can be — financial calculations are kept strictly deterministic to prevent model arithmetic errors.

**Provenance is the primary requirement.** A Balance Sheet holds figures at three levels — leaf line items, printed subtotals, section grand totals — and a ratio that mixes levels is wrong in a way that still looks plausible. One rule settles it:

> Prefer what the document printed and Module 1 validated. Derive only what was not printed.

So the three grand totals are Module 1's, read off the page and checked against the accounting equation. Current and non-current subtotals have to be summed from line items, because Module 2 excludes every printed subtotal and the figure does not exist in the data. Each result records which basis each of its sides used, so the mixed authority is disclosed rather than hidden.

That same exclusion makes summing safe: `line_items` holds leaves and only leaves, and the grand totals live in a different field, so nothing summable contains anything else summable. Double counting is structurally impossible — the engine re-applies Module 2's total-line predicate as a guard to prevent section doubling.

**Nothing is fabricated.** A ratio whose inputs are absent, or whose denominator is zero, is `unavailable` with a machine-readable reason — not infinity, not a bare `null`. A ratio computed from an incomplete set of line items is `partial`, naming the lines it left out and their total, so a reader can bound the true value rather than guess at it. **Nothing is clamped, either:** negative equity and negative working capital keep their signs and carry a warning, because hiding insolvency would be misleading.

Every figure is walkable back to ink on the page — canonical label → the label as printed → the figure as printed → page, row and column. Money is `Decimal` throughout; sums are exact, a quotient is rounded once at six decimal places, and working capital is never rounded at all.

The formulas, the fields each one draws on, and the limitations of each are generated into [`backend/docs/RATIOS.md`](backend/docs/RATIOS.md) from the declarations themselves. Where a ratio has competing accounting definitions — the quick ratio does — the choice and the rejected alternative are both written down.

### What Module 4 does

`POST /api/v1/documents/{id}/ask` answers a question about a processed Balance Sheet. It retrieves from what Modules 1–3 already stored — it never re-parses a file, never OCRs, never normalizes a term, and **never computes a figure**. The model explains numbers it is handed.

**The two retrieval paths are not symmetric, and that is the design.** Structured retrieval is a dictionary lookup on the already-loaded document: no I/O, no model, exact `Decimal`s with page/row/column references. It costs nothing, so it always runs, and it answers every financial question. Semantic search is the other half — chunks are tagged by page role, and the vector path is pointed at the **notes and accounting policies**, where prose actually lives.

**Nothing is fabricated, and three refusals never reach the model.** A question a Balance Sheet structurally cannot answer — revenue, profit, cash flow, next year — is refused deterministically. A metric outside the seven ratios is refused with the list of ones that exist. When nothing relevant is retrieved, that is said rather than filled in. A refusal is a `200` carrying a machine-readable reason.

**Every figure in an answer must appear in its context.** The answer's figures are matched against the ones supplied; unmatched means the model calculated or invented a number, triggering a single regeneration prompt before falling back to a refusal. Matching tolerates rounding, percentages, scale words, and digit groupings so legitimate formatting variations pass.

**Citations cannot be fabricated.** The response schema's citation list is an `enum` built per request from the tags actually in the context, which Ollama compiles into a decoding grammar — so citing a source that was not supplied is structurally unreachable.

Document text is treated as **untrusted input**: it is fenced, labelled as data, stripped of control characters, and prevented from closing its own block.

Retrieval is scoped by `document_id`, which is a required argument of every retrieval function and a declared filter field on the vector index, so one document's text can never surface in another's answer.

Embeddings and chunks live in **MongoDB Atlas** — no separate vector database. Indexing is lazy: an upload is unchanged, and a document is embedded the first time somebody asks about it.

Full reference: [`backend/docs/RAG.md`](backend/docs/RAG.md).

## Stack

React + Vite + TypeScript · Python + FastAPI · MongoDB Atlas

Module 1 parsing: **pdfplumber** (digital PDF text and tables) · **pypdfium2** (rasterisation) · **Tesseract** via pytesseract (OCR) · **openpyxl** (`.xlsx`)

Module 2 normalization: a **local** model through **Ollama**, reached over HTTP behind a provider interface. No paid API, and no data leaves the machine.

## Setup

Requires Python 3.11+, Node 18+, a MongoDB Atlas cluster, and — for scanned documents — the **Tesseract system binary**.

> **OCR needs Tesseract installed as a program, not just `pip install pytesseract`.**
> On Windows: `winget install UB-Mannheim.TesseractOCR`, then confirm with `tesseract --version`. Without it the API still runs and still handles every document that has a text layer; a scanned page is refused with a `503` rather than being silently read as blank.

> **Terminology normalization needs Ollama, also a separate program.**
> Install it from [ollama.com](https://ollama.com), then pull a model: `ollama pull qwen3:8b`. Without it the API still runs and still extracts every line item, figure and source reference; labels that are not already the canonical wording are recorded as `needs_review` rather than guessed at. Set `LLM_REQUIRED=true` to refuse instead of degrading.

> **Module 4 needs a second model** on Ollama for retrieval embeddings: `ollama pull nomic-embed-text` (274 MB). Without it questions are still answered from the structured figures Modules 1–3 computed; only the document-text half of retrieval is unavailable. Set `EMBEDDING_MODEL` accordingly.

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
pip install -r requirements.txt
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

## Notes

- Commands are PowerShell; chain with `;` rather than `&&`.
- OCR requires the **Tesseract system binary**; normalization requires **Ollama** with a model pulled. Neither is a pip package.
