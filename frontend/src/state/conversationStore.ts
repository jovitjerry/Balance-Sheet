import { askQuestion } from "../api/insights";
import type { Answer, Turn } from "../types/answers";
export interface Exchange {
  question: string;
  answer: Answer;
}
export interface Thread {
  exchanges: Exchange[];
  pending: string | null;
  error: unknown;
}
const NO_EXCHANGES: Exchange[] = [];
const EMPTY: Thread = { exchanges: NO_EXCHANGES, pending: null, error: null };
const threads = new Map<string, Thread>();
const listeners = new Set<() => void>();
export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
export function threadFor(documentId: string): Thread {
  return threads.get(documentId) ?? EMPTY;
}
function update(documentId: string, next: Partial<Thread>): void {
  const current = threadFor(documentId);
  threads.set(documentId, { ...current, ...next });
  for (const listener of listeners) listener();
}
export function ask(documentId: string, question: string): void {
  const trimmed = question.trim();
  if (!trimmed) return;
  const thread = threadFor(documentId);
  if (thread.pending !== null) return;
  update(documentId, { pending: trimmed, error: null });
  const history: Turn[] = thread.exchanges
    .filter((exchange) => exchange.answer.answer)
    .map((exchange) => ({
      question: exchange.question,
      answer: exchange.answer.answer ?? "",
    }));
  askQuestion(documentId, trimmed, history)
    .then((answer) => {
      update(documentId, {
        exchanges: [...threadFor(documentId).exchanges, { question: trimmed, answer }],
        pending: null,
      });
    })
    .catch((caught: unknown) => {
      update(documentId, { error: caught, pending: null });
    });
}
export function clear(documentId: string): void {
  update(documentId, { exchanges: [], error: null });
}
export function resetConversations(): void {
  threads.clear();
  for (const listener of listeners) listener();
}
