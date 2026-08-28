/**
 * Uploading a Balance Sheet and reading one back.
 *
 * The upload is deliberately not treated as a job: `POST /documents` runs
 * Modules 1-3 inline and returns the finished document, so this single request
 * can legitimately take minutes on a large sheet. There is no id to poll with,
 * because there is no id until it returns.
 */

import type { BalanceSheetDocument } from "../types/balanceSheet";
import { request } from "./client";

/**
 * Upload a file and run the pipeline over it.
 *
 * **A 201 does not mean the sheet was accepted.** A document that fails
 * validation - a missing total, or one that does not balance - comes back 201
 * with `status: "rejected"` and the evidence attached, because a rejected
 * submission is audit evidence rather than an error. Read `status`.
 */
export function uploadDocument(
  file: File,
  signal?: AbortSignal,
): Promise<BalanceSheetDocument> {
  const form = new FormData();
  form.append("file", file);
  return request<BalanceSheetDocument>("/documents", {
    method: "POST",
    form,
    signal,
  });
}

/** Fetch a stored document. Rejected submissions are retrievable too. */
export function getDocument(
  documentId: string,
  signal?: AbortSignal,
): Promise<BalanceSheetDocument> {
  return request<BalanceSheetDocument>(
    `/documents/${encodeURIComponent(documentId)}`,
    { signal },
  );
}
