/**
 * Module 4 - asking questions about a processed document.
 *
 * **A refusal is a 200.** "A Balance Sheet does not report profit" is the
 * correct answer to that question, so it arrives as a successful response
 * carrying `status: "refused"` and a machine-readable `reason`. Never branch on
 * the HTTP code to decide whether a question was answered.
 */

import type { Answer, IndexResult, Turn } from "../types/answers";
import { request } from "./client";

/** Mirrors `MAX_QUESTION_CHARS` in `modules/insights/router.py`. */
export const MAX_QUESTION_CHARS = 1000;

/**
 * Mirrors `MAX_HISTORY_TURNS` in `modules/insights/context.py`.
 *
 * The router declares it as `max_length` on the request model, so sending more
 * than this many turns is a 422 rather than something the backend quietly
 * trims. The slice in `askQuestion` is a correctness requirement, not a
 * courtesy.
 */
export const MAX_HISTORY_TURNS = 3;

/**
 * Ask about one document.
 *
 * History is sent by the client rather than held on the server: every turn
 * re-retrieves from the document anyway, so there is no session state worth
 * keeping, and none to get wrong.
 */
export function askQuestion(
  documentId: string,
  question: string,
  history: Turn[] = [],
  signal?: AbortSignal,
): Promise<Answer> {
  return request<Answer>(
    `/documents/${encodeURIComponent(documentId)}/ask`,
    {
      method: "POST",
      body: { question, history: history.slice(-MAX_HISTORY_TURNS) },
      signal,
    },
  );
}

/**
 * Rebuild a document's retrieval corpus.
 *
 * Not needed in normal use - the first question indexes lazily. Exposed for
 * the case where the embedding model changed and you would rather pay the cost
 * now than on somebody's next question.
 */
export function reindexDocument(
  documentId: string,
  signal?: AbortSignal,
): Promise<IndexResult> {
  return request<IndexResult>(
    `/documents/${encodeURIComponent(documentId)}/index`,
    { method: "POST", signal },
  );
}
