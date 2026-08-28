/**
 * Transport-level shapes: what the API says when it is not returning a
 * document or an answer.
 */

export interface HealthResponse {
  status: string;
  database: "connected" | "unavailable";
}

export type StageState = "implemented" | "partial" | "not_implemented";

/**
 * `trigger` distinguishes the stages an upload runs from Module 4, which is
 * built but answers questions on request - a distinction `state` alone cannot
 * make without misreporting one or the other.
 */
export interface PipelineStageInfo {
  stage: "ingest" | "extract" | "ratios" | "insights";
  module: number;
  description: string;
  state: StageState;
  trigger: string;
}

export interface PipelineStatus {
  stages: PipelineStageInfo[];
}

/**
 * The error envelope from `backend/app/core/errors.py`. Every message in it is
 * one the backend wrote deliberately - no stack traces, paths or connection
 * strings - so it is safe to show a user verbatim.
 */
export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
  };
}

/** Error codes the backend can return, from `core/errors.py` and the routers. */
export type ApiErrorCode =
  | "invalid_upload"
  | "unreadable_document"
  | "not_a_balance_sheet"
  | "document_not_found"
  | "document_not_ready"
  | "storage_error"
  | "stage_not_implemented"
  | "internal_error";
