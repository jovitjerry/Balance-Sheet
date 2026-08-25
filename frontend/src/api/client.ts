/** Thin API client. Requests go to /api and Vite proxies them to the backend. */

import type {
  BalanceSheetDocument,
  HealthResponse,
  PipelineStatus,
} from "../types/balanceSheet";

const BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, init);

  if (!response.ok) {
    // The backend renders domain errors as { error: { code, message } }.
    let message = `${response.status} ${response.statusText}`;
    let code: string | undefined;
    try {
      const body = await response.json();
      if (body?.error) {
        message = body.error.message ?? message;
        code = body.error.code;
      } else if (body?.detail) {
        message = typeof body.detail === "string" ? body.detail : message;
      }
    } catch {
      // Non-JSON error body; the status line above is the best we have.
    }
    throw new ApiError(message, response.status, code);
  }

  return (await response.json()) as T;
}

export const getHealth = () => request<HealthResponse>("/health");

export const getPipelineStatus = () => request<PipelineStatus>("/pipeline");

export function uploadDocument(file: File): Promise<BalanceSheetDocument> {
  const form = new FormData();
  form.append("file", file);
  return request<BalanceSheetDocument>("/documents", {
    method: "POST",
    body: form,
  });
}
