/**
 * The transport. Requests go to /api and Vite proxies them to the backend.
 *
 * Every caller-visible error message the backend produces is one it wrote
 * deliberately - `core/errors.py` renders domain errors as
 * `{error: {code, message}}` and its router tests assert that no stack trace,
 * path, library name or connection string reaches a response. That is what
 * makes it safe to show `ApiError.message` to a user verbatim.
 */

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

/**
 * Whether a rejected request was cancelled rather than failed.
 *
 * Callers abort on unmount and on document change, so this is the common case,
 * not an exceptional one - and reporting a deliberate cancellation to the user
 * as an error would be a lie about what happened.
 */
export function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

interface RequestOptions {
  method?: string;
  /** Sent as JSON. Mutually exclusive with `form`. */
  body?: unknown;
  /** Sent as multipart. The browser sets the boundary, so we set no headers. */
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
    // Deliberately no Content-Type: fetch must generate the multipart
    // boundary itself, and setting the header by hand omits it.
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
    // A network-level failure: the backend is not running, or the connection
    // dropped. Status 0 marks it as never having reached the server.
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
      // FastAPI's own validation errors do not use the envelope above.
      message = payload.detail;
    } else if (Array.isArray(payload?.detail)) {
      const first = payload.detail[0] as { msg?: string } | undefined;
      if (first?.msg) message = first.msg;
    }
  } catch {
    // Non-JSON error body; the status line is the best we have.
  }

  return new ApiError(message, response.status, code);
}
