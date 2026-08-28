/**
 * Module 4 response shapes, mirroring `backend/app/core/schemas.py`.
 *
 * The rule that governs every consumer of these types: **a refusal is a 200**.
 * "A Balance Sheet does not report profit" is the correct answer to that
 * question, not a failure, so it arrives as a successful response carrying a
 * machine-readable `reason`. Branch on `status`, never on an HTTP code.
 */

import type { SourceRef, Timestamp } from "./balanceSheet";

/**
 * Which retrieval paths a question was sent down. Decided by rules, not by a
 * model, so the same question always routes the same way.
 */
export type RetrievalRoute = "structured" | "text" | "both" | "out_of_scope";

export type EvidenceKind =
  | "section_total"
  | "line_item"
  | "ratio"
  | "equation"
  | "coverage"
  /** A passage quoted from the document's own text. */
  | "text";

/**
 * One grounded piece of support, and where it came from. `id` is the tag the
 * model cites - "F1", "R1", "C1".
 */
export interface Evidence {
  id: string;
  kind: EvidenceKind;
  /** What this is, in the document's own words where it has any. */
  label: string;
  /** The figure, as a string. Money is never serialised as a JSON number. */
  value?: string | null;
  /** Formula, unavailability reason, or stated limitation. */
  detail?: string | null;
  /** The passage, for TEXT evidence. */
  quote?: string | null;
  page_index?: number | null;
  source?: SourceRef | null;
  chunk_id?: string | null;
}

/**
 * `degraded` means no model was reachable, so the stored figures come back
 * without prose. The figures are already computed; withholding them because a
 * language model is offline would help nobody.
 */
export type AnswerStatus = "answered" | "refused" | "degraded";

/**
 * Whether every figure in the answer traces back to supplied context. The
 * direct answer to a measured failure: a candidate model once summed current
 * assets as 550,000 against a true 850,000 and concluded the company could not
 * pay its bills.
 */
export interface Verification {
  passed: boolean;
  figures_verified: string[];
  figures_unverified: string[];
  /** Whether generation was retried after a failed check. */
  retried: boolean;
}

/**
 * Why an answer refused. A closed set, from
 * `backend/app/modules/insights/service.py`.
 */
export type RefusalReason =
  | "out_of_scope"
  | "unsupported_metric"
  | "no_context"
  | "insufficient_context"
  | "unverifiable_figures"
  | "malformed_response"
  | "llm_unavailable";

/** A grounded reply to one question about one document. */
export interface Answer {
  document_id: string;
  question: string;
  /** null only when status is "degraded". */
  answer?: string | null;
  status: AnswerStatus;
  route: RetrievalRoute;
  /** The authoritative facts placed in context, cited or not. */
  supporting_facts: Evidence[];
  /** What the model actually cited, resolved. Unresolvable tags are dropped. */
  citations: Evidence[];
  verification: Verification;
  reason?: RefusalReason | string | null;
  /** null when no model was called. */
  model?: string | null;
  spec_version: string;
  created_at: Timestamp;
}

/** One earlier exchange, sent back with the next question. */
export interface Turn {
  question: string;
  answer: string;
}

/** Result of `POST /documents/{id}/index`. */
export interface IndexResult {
  indexed: boolean;
  chunks: number;
  embedding_model?: string;
  chunk_spec_version?: string;
  reason?: string;
}
