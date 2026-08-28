/**
 * The question thread for one document.
 *
 * Keyed by document id and reset whenever that id changes. That mirrors the
 * backend, where `Context.groundable` deliberately excludes conversation
 * history from admissible evidence: history is shown to the model so that "is
 * that good?" can be resolved, and is never allowed to become a fact. Carrying
 * a thread across documents would defeat that on the client side instead.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { isAbort } from "../api/client";
import { askQuestion } from "../api/insights";
import type { Answer, Turn } from "../types/answers";

export interface Exchange {
  question: string;
  answer: Answer;
}

export function useConversation(documentId: string) {
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  const controllerRef = useRef<AbortController | null>(null);
  /** The document whose answers we are still willing to accept. */
  const wanted = useRef(documentId);

  useEffect(() => {
    wanted.current = documentId;
    controllerRef.current?.abort();
    controllerRef.current = null;
    setExchanges([]);
    setPending(null);
    setError(null);
  }, [documentId]);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const ask = useCallback(
    (question: string) => {
      const trimmed = question.trim();
      if (!trimmed) return;

      const controller = new AbortController();
      controllerRef.current = controller;
      setPending(trimmed);
      setError(null);

      // Only answered turns are sent back. A refusal carries no content the
      // next question could build on, and a degraded turn has no prose at all.
      const history: Turn[] = exchanges
        .filter((exchange) => exchange.answer.answer)
        .map((exchange) => ({
          question: exchange.question,
          answer: exchange.answer.answer ?? "",
        }));

      askQuestion(documentId, trimmed, history, controller.signal)
        .then((answer) => {
          if (wanted.current !== documentId) return;
          setExchanges((current) => [...current, { question: trimmed, answer }]);
          setPending(null);
        })
        .catch((caught: unknown) => {
          if (isAbort(caught)) return;
          if (wanted.current !== documentId) return;
          setError(caught);
          setPending(null);
        });
    },
    [documentId, exchanges],
  );

  const clear = useCallback(() => {
    setExchanges([]);
    setError(null);
  }, []);

  return { exchanges, pending, error, ask, clear };
}
