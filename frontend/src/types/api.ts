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
  trigger: string;
}
export interface PipelineStatus {
  stages: PipelineStageInfo[];
}
export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
  };
}
export type ApiErrorCode =
  | "invalid_upload"
  | "unreadable_document"
  | "not_a_balance_sheet"
  | "document_not_found"
  | "document_not_ready"
  | "storage_error"
  | "stage_not_implemented"
  | "internal_error";
