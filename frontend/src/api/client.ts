import type { ErrorEnvelope } from "../types/api";
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
export function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
interface RequestOptions {
  method?: string;
  body?: unknown;
  form?: FormData;
  signal?: AbortSignal;
}
export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { method = "GET", body, form, signal } = options;
  const init: RequestInit = { method, signal };
  if (form !== undefined) {
    init.body = form;
  } else if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, init);
  } catch (error) {
    if (isAbort(error)) throw error;
    throw new ApiError(
      "Could not reach the API. Is the backend running on port 8000?",
      0,
      "network_error",
    );
  }
  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
async function toApiError(response: Response): Promise<ApiError> {
  let message = `${response.status} ${response.statusText}`.trim();
  let code: string | undefined;
  try {
    const payload = (await response.json()) as Partial<ErrorEnvelope> & {
      detail?: unknown;
    };
    if (payload?.error) {
      message = payload.error.message ?? message;
      code = payload.error.code;
    } else if (typeof payload?.detail === "string") {
      message = payload.detail;
    } else if (Array.isArray(payload?.detail)) {
      const first = payload.detail[0] as { msg?: string } | undefined;
      if (first?.msg) message = first.msg;
    }
  } catch {
  }
  return new ApiError(message, response.status, code);
}
