export type Money = string;
export type Timestamp = string;
export type IsoDate = string;
export type DocumentStatus =
  | "uploaded"
  | "parsed"
  | "validated"
  | "extracted"
  | "analyzed"
  | "rejected"
  | "failed";
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
export interface PositionedWord {
  text: string;
  left: number;
  top: number;
  width: number;
  height: number;
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
export type ExtractionStatus = "extracted" | "unparsed_value";
export type NormalizationStatus =
  | "normalized"
  | "needs_review"
  | "unmapped"
  | "unavailable";
export type NormalizationMethod = "dictionary" | "cache" | "llm" | "unavailable";
export interface Normalization {
  canonical_label?: string | null;
  status: NormalizationStatus;
  method: NormalizationMethod;
  confidence?: number | null;
  taxonomy_version: string;
  model?: string | null;
  reason?: string | null;
}
export interface LineItem {
  label: string;
  value?: Money | null;
  raw?: string | null;
  subsection?: string | null;
  source?: SourceRef | null;
  status: ExtractionStatus;
  normalization?: Normalization | null;
}
export interface BalanceSheetSection {
  total: Money;
  total_label?: string | null;
  total_raw?: string | null;
  total_source?: SourceRef | null;
  line_items: LineItem[];
  line_items_total?: Money | null;
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
  normalization_summary?: Record<string, number> | null;
}
export type RatioStatus = "ok" | "partial" | "unavailable";
export type RatioUnit = "ratio" | "currency";
export type RatioBasis = "section_total" | "derived_sum" | "composite";
export interface RatioInput {
  canonical_label?: string | null;
  label: string;
  value: Money;
  source?: SourceRef | null;
}
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
  excluded: RatioInput[];
  excluded_value?: Money | null;
  reason?: string | null;
  warnings: string[];
}
export interface RatioDiagnostics {
  duplicate_canonical_labels: Record<string, number>;
  reconciliation_difference: Record<string, Money>;
  normalization_summary: Record<string, number>;
  unclassified: RatioInput[];
}
export interface RatioSet {
  ratios: RatioResult[];
  spec_version: string;
  taxonomy_version?: string | null;
  currency?: string | null;
  scale_label?: string | null;
  diagnostics: RatioDiagnostics;
  warnings: string[];
  computed_at: Timestamp;
}
export interface ChunkIndexState {
  indexed_at: Timestamp;
  embedding_model: string;
  embedding_dim: number;
  chunk_spec_version: string;
  chunk_count: number;
}
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
  end_date?: IsoDate | null;
  year?: number | null;
  source: SourceRef;
}
export interface PeriodSelection {
  selected: PeriodCandidate;
  candidates: PeriodCandidate[];
  reason: string;
}
export interface UnitHint {
  currency?: string | null;
  scale_label?: string | null;
  scale_factor?: Money | null;
  source?: SourceRef | null;
}
export interface ValidationSummary {
  required_fields_present: boolean;
  missing_fields: string[];
  equation_balanced?: boolean | null;
  passed: boolean;
}
export interface Rejection {
  reason: RejectionReason;
  message: string;
  at: Timestamp;
}
export interface EquationCheck {
  total_assets: Money;
  total_liabilities: Money;
  total_equity: Money;
  expected: Money;
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
  identification?: IdentificationEvidence | null;
  period?: PeriodSelection | null;
  units?: UnitHint | null;
  extracted?: ExtractedBalanceSheet | null;
  ratios?: RatioSet | null;
  chunk_index?: ChunkIndexState | null;
  equation_check?: EquationCheck | null;
  validation?: ValidationSummary | null;
  rejection?: Rejection | null;
  errors: string[];
  created_at: Timestamp;
  updated_at: Timestamp;
}
