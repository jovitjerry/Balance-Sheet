/**
 * Mirrors the Pydantic schemas in `backend/app/core/schemas.py`.
 *
 * Kept hand-written and side-by-side with the backend rather than generated,
 * so a divergence is visible in review. Monetary amounts arrive as strings:
 * the backend stores Decimal and must never round-trip money through a
 * JavaScript number.
 *
 * Scope: single reporting period. No year-over-year structure here.
 */

/** A monetary amount, serialized as a string to preserve exact precision. */
export type Money = string;

export type DocumentStatus =
  | "uploaded"
  | "parsed"
  | "validated"
  | "rejected"
  | "failed";

/** `pdf_mixed`: some pages carried a text layer, others were scanned. */
export type ParserKind = "pdf_text" | "pdf_ocr" | "pdf_mixed" | "excel";

export type RejectionReason =
  | "unreadable"
  | "not_a_balance_sheet"
  | "missing_required_fields"
  | "equation_unbalanced";

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

export interface LineItem {
  label: string;
  value: Money;
  source?: SourceRef | null;
}

export interface BalanceSheetSection {
  total: Money;
  total_label?: string | null;
  /** The total as printed, e.g. "(2,300)". Kept beside the parsed value. */
  total_raw?: string | null;
  total_source?: SourceRef | null;
  /** Empty until Module 2 extracts line items. */
  line_items: LineItem[];
}

export interface ExtractedBalanceSheet {
  entity_name?: string | null;
  period_label?: string | null;
  period_end_date?: string | null;
  currency?: string | null;
  assets: BalanceSheetSection;
  liabilities: BalanceSheetSection;
  equity: BalanceSheetSection;
}

/** Total Assets = Total Liabilities + Shareholders' Equity */
export interface EquationCheck {
  total_assets: Money;
  total_liabilities: Money;
  total_equity: Money;
  expected: Money;
  /** Signed: positive means assets exceed liabilities plus equity. */
  difference: Money;
  tolerance_applied: Money;
  balanced: boolean;
}

/** One piece of evidence for or against the document being a Balance Sheet. */
export interface IdentificationSignal {
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
  end_date?: string | null;
  year?: number | null;
  source: SourceRef;
}

/**
 * Single-period scope. On a comparative sheet the most recent period is
 * selected; the others are recorded for traceability and never analysed.
 * This is deliberately not a year-over-year comparison.
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
  message: string;
  at: string;
}

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
  equation_check?: EquationCheck | null;
  validation?: ValidationSummary | null;
  rejection?: Rejection | null;
  errors: string[];
  created_at: string;
  updated_at: string;
}

export interface HealthResponse {
  status: string;
  database: "connected" | "unavailable";
}

export type StageState = "implemented" | "partial" | "not_implemented";

export interface PipelineStageInfo {
  stage: "ingest" | "extract" | "ratios" | "insights";
  module: number;
  description: string;
  state: StageState;
}

export interface PipelineStatus {
  stages: PipelineStageInfo[];
}
