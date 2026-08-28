/**
 * Turning an API error into something a reader can act on.
 *
 * The backend's own message is always shown: `core/errors.py` guarantees it
 * carries no stack trace, path, library name or connection string, and
 * `test_router.py::TestResponsesLeakNothing` enforces that. What is added here
 * is the next step, which the backend has no way to know.
 */

import { ApiError } from "../api/client";

export interface ErrorGuidance {
  /** The backend's own words, or a written fallback. */
  message: string;
  /** What to do about it. Empty when there is nothing useful to say. */
  guidance: string;
  /** Whether retrying the same request could plausibly work. */
  retryable: boolean;
}

const BY_CODE: Record<string, Omit<ErrorGuidance, "message">> = {
  invalid_upload: {
    guidance:
      "Choose a PDF or .xlsx Balance Sheet under 25 MB. The file is checked " +
      "by its contents, not its extension, so a renamed file is refused here.",
    retryable: false,
  },
  unreadable_document: {
    guidance:
      "The file was accepted but no text could be read from it. A scanned PDF " +
      "needs OCR, which requires the Tesseract system binary on the server.",
    retryable: false,
  },
  not_a_balance_sheet: {
    guidance:
      "This system analyses Balance Sheets only - not Income Statements or " +
      "Cash Flow Statements. Nothing was stored.",
    retryable: false,
  },
  document_not_found: {
    guidance:
      "The document is no longer in the database. It may have been removed, " +
      "or this link may be from a different environment.",
    retryable: false,
  },
  document_not_ready: {
    guidance:
      "Questions can only be asked about a document that finished extraction " +
      "and was not rejected during validation.",
    retryable: false,
  },
  storage_error: {
    guidance: "The file store could not be reached. This is a server problem.",
    retryable: true,
  },
  stage_not_implemented: {
    guidance: "That part of the pipeline has not been built yet.",
    retryable: false,
  },
  network_error: {
    guidance:
      "Start the backend with: uvicorn app.main:app --reload, then try again.",
    retryable: true,
  },
  // Raised by the dev server's proxy when nothing is listening on port 8000.
  // Without it a refused connection arrives as a plain 500 and gets reported
  // as a server fault, which contradicts the header saying it is unreachable.
  backend_unreachable: {
    guidance:
      "Nothing is listening on port 8000. Start the backend with: " +
      "uvicorn app.main:app --reload, then try again.",
    retryable: true,
  },
};

const BY_STATUS: Record<number, Omit<ErrorGuidance, "message">> = {
  413: {
    guidance: "The file exceeds the 25 MB upload limit.",
    retryable: false,
  },
  422: {
    guidance: "The request was understood but could not be processed.",
    retryable: false,
  },
  503: {
    guidance:
      "A capability this request needs is unavailable - OCR, or the local " +
      "model. Check that Ollama is running and the model is pulled.",
    retryable: true,
  },
  500: {
    guidance: "Something went wrong on the server.",
    retryable: true,
  },
  502: {
    guidance: "The API could not be reached. Check that it is running.",
    retryable: true,
  },
  504: {
    guidance: "The API did not respond in time.",
    retryable: true,
  },
};

export function describeError(error: unknown): ErrorGuidance {
  if (error instanceof ApiError) {
    const known =
      (error.code ? BY_CODE[error.code] : undefined) ?? BY_STATUS[error.status];
    return {
      message: error.message,
      guidance: known?.guidance ?? "",
      retryable: known?.retryable ?? false,
    };
  }

  if (error instanceof Error) {
    return { message: error.message, guidance: "", retryable: false };
  }

  return {
    message: "Something went wrong.",
    guidance: "",
    retryable: false,
  };
}
