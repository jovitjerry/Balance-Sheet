import type { Answer, IndexResult, Turn } from "../types/answers";
import { request } from "./client";
export const MAX_QUESTION_CHARS = 1000;
export const MAX_HISTORY_TURNS = 3;
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
export function reindexDocument(
  documentId: string,
  signal?: AbortSignal,
): Promise<IndexResult> {
  return request<IndexResult>(
    `/documents/${encodeURIComponent(documentId)}/index`,
    { method: "POST", signal },
  );
}
