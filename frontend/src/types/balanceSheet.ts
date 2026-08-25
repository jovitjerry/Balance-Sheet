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

export type ParserKind = "pdf_text" | "pdf_ocr" | "excel";

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
  row?: number | null;
  column?: number | null;
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

export interface BalanceSheetDocument {
  _id?: string | null;
  status: DocumentStatus;
  source: SourceFile;
  preliminary?: PreliminaryExtraction | null;
  preliminary_ref?: StorageRef | null;
  extracted?: ExtractedBalanceSheet | null;
  equation_check?: EquationCheck | null;
  errors: string[];
  created_at: string;
  updated_at: string;
}

export interface HealthResponse {
  status: string;
  database: "connected" | "unavailable";
}

export type StageState = "partial" | "not_implemented";

export interface PipelineStageInfo {
  stage: "ingest" | "extract" | "ratios" | "insights";
  module: number;
  description: string;
  state: StageState;
}

export interface PipelineStatus {
  stages: PipelineStageInfo[];
}
