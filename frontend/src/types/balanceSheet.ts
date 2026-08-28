/**
 * Mirrors the Pydantic schemas in `backend/app/core/schemas.py`.
 *
 * Kept hand-written and side-by-side with the backend rather than generated,
 * so a divergence is visible in review. Monetary amounts arrive as strings:
 * the backend stores Decimal and must never round-trip money through a
 * JavaScript number. `backend/tests/modules/ingestion/test_router.py` asserts
 * that serialization, so this is a contract and not an assumption.
 *
 * Scope: single reporting period. No year-over-year structure here.
 *
 * FastAPI serializes response models `by_alias`, so the document id arrives as
 * `_id` rather than `id`.
 */

/** A monetary amount, serialized as a string to preserve exact precision. */
export type Money = string;

/** An ISO 8601 timestamp. */
export type Timestamp = string;

/** An ISO 8601 date, no time component. */
export type IsoDate = string;

export type DocumentStatus =
  | "uploaded"
  | "parsed"
  | "validated"
  /** Module 2 has extracted the line items and normalized their labels. */
  | "extracted"
  /** Module 3 has computed the ratios. */
  | "analyzed"
  | "rejected"
  | "failed";

/** `pdf_mixed`: some pages carried a text layer, others were scanned. */
export type ParserKind = "pdf_text" | "pdf_ocr" | "pdf_mixed" | "excel";

export type RejectionReason =
  | "unreadable"
  | "not_a_balance_sheet"
  | "missing_required_fields"
  | "equation_unbalanced";

// --------------------------------------------------------------------------
// Storage
// --------------------------------------------------------------------------

export interface StorageRef {
  backend: string;
  key: string;
  size_bytes: number;
  content_type: string;
}

export interface SourceFile {
  filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  ref: StorageRef;
}

// --------------------------------------------------------------------------
// Preliminary extraction - raw parser output
// --------------------------------------------------------------------------

export interface SourceRef {
  page_index: number;
  sheet_name?: string | null;
  row?: number | null;
  column?: number | null;
}

/**
 * A word and the box it occupied. Recorded for scanned pages (from OCR) and
 * digital ones (from the PDF text layer) alike - a Balance Sheet's column
 * positions are what identify its reporting period.
 */
export interface PositionedWord {
  text: string;
  left: number;
  top: number;
  width: number;
  height: number;
  /** OCR confidence 0-100; null for digital text, which was read not guessed. */
  confidence?: number | null;
}

export interface RawTable {
  rows: (string | null)[][];
}

export interface SourcePage {
  index: number;
  name?: string | null;
  text: string;
  tables: RawTable[];
  ocr_used: boolean;
  ocr_confidence?: number | null;
  words: PositionedWord[];
  page_width?: number | null;
  page_height?: number | null;
}

export interface PreliminaryExtraction {
  parser: ParserKind;
  pages: SourcePage[];
  warnings: string[];
}

// --------------------------------------------------------------------------
// Structured extraction (Module 2)
// --------------------------------------------------------------------------

/**
 * `unparsed_value`: the label was found but its figure would not parse. The
 * line is kept anyway - dropping it would quietly shrink the Balance Sheet.
 */
export type ExtractionStatus = "extracted" | "unparsed_value";

/**
 * `needs_review` is a real answer, not a failure. Forcing a canonical label
 * onto one nobody understood would put a confident wrong category into the
 * ratios.
 */
export type NormalizationStatus =
  | "normalized"
  | "needs_review"
  | "unmapped"
  | "unavailable";

export type NormalizationMethod = "dictionary" | "cache" | "llm" | "unavailable";

/** The terminology decision for one line item, and who made it. */
export interface Normalization {
  canonical_label?: string | null;
  status: NormalizationStatus;
  method: NormalizationMethod;
  /**
   * The model's own stated confidence, NOT a calibrated probability. It may
   * demote a mapping to needs_review and may never rescue a failed one.
   */
  confidence?: number | null;
  taxonomy_version: string;
  model?: string | null;
  reason?: string | null;
}

/**
 * `label` is the document's own wording and is never overwritten -
 * `normalization.canonical_label` sits beside it.
 */
export interface LineItem {
  label: string;
  /** null when the printed figure would not parse. */
  value?: Money | null;
  /** The figure exactly as printed, e.g. "(2,300)". */
  raw?: string | null;
  /** "current" or "non_current" where the sheet says. */
  subsection?: string | null;
  source?: SourceRef | null;
  status: ExtractionStatus;
  normalization?: Normalization | null;
}

export interface BalanceSheetSection {
  total: Money;
  total_label?: string | null;
  /** The total as printed, e.g. "(2,300)". Kept beside the parsed value. */
  total_raw?: string | null;
  total_source?: SourceRef | null;
  line_items: LineItem[];
  line_items_total?: Money | null;
  /**
   * total - line_items_total, signed. Diagnostic only: subtotals and rounding
   * make exact agreement unusual, so this never rejects a document. It is not
   * the accounting equation, which is Module 1's.
   */
  reconciliation_difference?: Money | null;
}

export interface ExtractedBalanceSheet {
  entity_name?: string | null;
  period_label?: string | null;
  period_end_date?: IsoDate | null;
  currency?: string | null;
  assets: BalanceSheetSection;
  liabilities: BalanceSheetSection;
  equity: BalanceSheetSection;
  taxonomy_version?: string | null;
  /** Line-item counts by NormalizationStatus. */
  normalization_summary?: Record<string, number> | null;
}

// --------------------------------------------------------------------------
// Module 3 - ratios
// --------------------------------------------------------------------------

/**
 * `partial` is the honest middle: the figure is real, but a line that should
 * have contributed was left out because nobody could classify it.
 */
export type RatioStatus = "ok" | "partial" | "unavailable";

/**
 * Working capital is money and inherits the sheet's printed scale; the other
 * six are dimensionless, so scale cancels out of them entirely.
 */
export type RatioUnit = "ratio" | "currency";

/**
 * Which level of the document a figure was taken from. Recorded per side
 * because Module 3 mixes levels deliberately: grand totals are Module 1's
 * printed, equation-checked figures, while current/non-current subtotals are
 * summed from line items.
 */
export type RatioBasis = "section_total" | "derived_sum" | "composite";

export interface RatioInput {
  /** null on an excluded input, which is precisely why it was excluded. */
  canonical_label?: string | null;
  label: string;
  value: Money;
  source?: SourceRef | null;
}

/**
 * `numerator` and `denominator` are stored unrounded so any consumer can
 * re-derive `value` at any precision.
 */
export interface RatioResult {
  name: string;
  formula: string;
  definition: string;
  unit: RatioUnit;
  status: RatioStatus;
  value?: Money | null;
  numerator?: Money | null;
  denominator?: Money | null;
  numerator_basis?: RatioBasis | null;
  denominator_basis?: RatioBasis | null;
  numerator_inputs: RatioInput[];
  denominator_inputs: RatioInput[];
  /** Lines that would have contributed had they been classified. */
  excluded: RatioInput[];
  /**
   * Sum of the excluded figures. The reported value and the value with this
   * added bound the true one.
   */
  excluded_value?: Money | null;
  /** Machine-readable, from a closed set. Why there is no value. */
  reason?: string | null;
  warnings: string[];
}

export interface RatioDiagnostics {
  /** Canonical labels claimed by more than one line, and by how many. */
  duplicate_canonical_labels: Record<string, number>;
  /** Per section, Module 2's total-minus-line-items difference. */
  reconciliation_difference: Record<string, Money>;
  normalization_summary: Record<string, number>;
  unclassified: RatioInput[];
}

export interface RatioSet {
  ratios: RatioResult[];
  spec_version: string;
  taxonomy_version?: string | null;
  currency?: string | null;
  /** e.g. "in thousands". Recorded, NOT applied. */
  scale_label?: string | null;
  diagnostics: RatioDiagnostics;
  warnings: string[];
  computed_at: Timestamp;
}

// --------------------------------------------------------------------------
// Module 4 - retrieval index state
// --------------------------------------------------------------------------

export interface ChunkIndexState {
  indexed_at: Timestamp;
  embedding_model: string;
  embedding_dim: number;
  chunk_spec_version: string;
  chunk_count: number;
}

// --------------------------------------------------------------------------
// Module 1 evidence
// --------------------------------------------------------------------------

export interface IdentificationSignal {
  /** "title", "section_header", "total_line" or "equation_terms". */
  kind: string;
  text: string;
  weight: number;
  source: SourceRef;
}

export interface IdentificationEvidence {
  is_balance_sheet: boolean;
  score: number;
  threshold: number;
  signals: IdentificationSignal[];
}

export interface PeriodCandidate {
  label: string;
  end_date?: IsoDate | null;
  year?: number | null;
  source: SourceRef;
}

/**
 * Single-period scope. On a comparative sheet the most recent period is
 * selected; the others are recorded for traceability and never analysed.
 */
export interface PeriodSelection {
  selected: PeriodCandidate;
  candidates: PeriodCandidate[];
  reason: string;
}

/** Currency and magnitude as printed. Recorded only - never applied. */
export interface UnitHint {
  currency?: string | null;
  scale_label?: string | null;
  /** What `scale_label` means numerically. NOT applied to the figures. */
  scale_factor?: Money | null;
  source?: SourceRef | null;
}

export interface ValidationSummary {
  required_fields_present: boolean;
  missing_fields: string[];
  /** null when the equation could not be evaluated. */
  equation_balanced?: boolean | null;
  passed: boolean;
}

export interface Rejection {
  reason: RejectionReason;
  /** Safe for display. No paths, no stack traces. */
  message: string;
  at: Timestamp;
}

/** Total Assets = Total Liabilities + Shareholders' Equity */
export interface EquationCheck {
  total_assets: Money;
  total_liabilities: Money;
  total_equity: Money;
  /** total_liabilities + total_equity */
  expected: Money;
  /** total_assets - expected, signed. */
  difference: Money;
  tolerance_applied: Money;
  balanced: boolean;
}

// --------------------------------------------------------------------------
// The document
// --------------------------------------------------------------------------

export interface BalanceSheetDocument {
  _id?: string | null;
  status: DocumentStatus;
  source: SourceFile;
  preliminary?: PreliminaryExtraction | null;
  preliminary_ref?: StorageRef | null;
  identification?: IdentificationEvidence | null;
  period?: PeriodSelection | null;
  units?: UnitHint | null;
  extracted?: ExtractedBalanceSheet | null;
  ratios?: RatioSet | null;
  /** Module 4 indexes lazily, so most documents never carry this. */
  chunk_index?: ChunkIndexState | null;
  equation_check?: EquationCheck | null;
  validation?: ValidationSummary | null;
  rejection?: Rejection | null;
  errors: string[];
  created_at: Timestamp;
  updated_at: Timestamp;
}
