import type { SourceRef, Timestamp } from "./balanceSheet";
export type RetrievalRoute = "structured" | "text" | "both" | "out_of_scope";
export type EvidenceKind =
  | "section_total"
  | "line_item"
  | "ratio"
  | "equation"
  | "coverage"
  | "text";
export interface Evidence {
  id: string;
  kind: EvidenceKind;
  label: string;
  value?: string | null;
  detail?: string | null;
  quote?: string | null;
  page_index?: number | null;
  source?: SourceRef | null;
  chunk_id?: string | null;
}
export type AnswerStatus = "answered" | "refused" | "degraded";
export interface Verification {
  passed: boolean;
  figures_verified: string[];
  figures_unverified: string[];
  retried: boolean;
}
export type RefusalReason =
  | "out_of_scope"
  | "unsupported_metric"
  | "no_context"
  | "insufficient_context"
  | "unverifiable_figures"
  | "malformed_response"
  | "llm_unavailable";
export interface Answer {
  document_id: string;
  question: string;
  answer?: string | null;
  status: AnswerStatus;
  route: RetrievalRoute;
  supporting_facts: Evidence[];
  citations: Evidence[];
  verification: Verification;
  reason?: RefusalReason | string | null;
  model?: string | null;
  spec_version: string;
  created_at: Timestamp;
}
export interface Turn {
  question: string;
  answer: string;
}
export interface IndexResult {
  indexed: boolean;
  chunks: number;
  embedding_model?: string;
  chunk_spec_version?: string;
  reason?: string;
}
