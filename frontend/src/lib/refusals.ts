/**
 * What a refusal means, in plain English.
 *
 * The seven codes are the closed set defined in
 * `modules/insights/service.py`. A refusal is a **correct outcome**, not an
 * error - "a Balance Sheet does not report profit" is the right answer to that
 * question - so none of this copy apologises, and none of it is coloured red.
 *
 * `unverifiable_figures` is the one worth reading twice. It means the model
 * produced a figure that could not be traced to the context, and the answer
 * was withheld rather than shown. That is the safety net doing its job, and it
 * is described that way.
 */

import type { RefusalReason } from "../types/answers";

export interface RefusalCopy {
  title: string;
  explanation: string;
  /** What the reader can usefully do instead. */
  suggestion?: string;
}

const COPY: Record<RefusalReason, RefusalCopy> = {
  out_of_scope: {
    title: "A Balance Sheet cannot answer that",
    explanation:
      "A Balance Sheet reports what a company owns and owes at a single date. " +
      "It has no revenue, profit or cash flow line to find, and this system " +
      "analyses no other statement.",
    suggestion:
      "Ask about assets, liabilities, equity, or the liquidity and leverage " +
      "ratios derived from them.",
  },
  unsupported_metric: {
    title: "That metric is not computed",
    explanation:
      "This system computes seven Balance Sheet ratios and will not derive " +
      "another. A figure produced by a language model rather than by the " +
      "calculation engine would look identical to a correct one and be " +
      "unverifiable.",
    suggestion: "The seven are on the Ratios tab.",
  },
  no_context: {
    title: "Nothing in this document answers that",
    explanation:
      "The stored figures and the document's own text were both searched, and " +
      "no relevant figure or passage was found.",
  },
  insufficient_context: {
    title: "Not enough in this document to answer",
    explanation:
      "Related material was found, but not enough to answer the question " +
      "without filling the gap from general knowledge — which would produce a " +
      "confident answer this document does not support.",
  },
  unverifiable_figures: {
    title: "The answer was withheld",
    explanation:
      "A figure in the drafted answer could not be traced back to the " +
      "document, so the answer was not shown. Generation is retried once " +
      "before this point is reached.",
    suggestion:
      "This is the grounding check working as intended. Rephrasing the " +
      "question often helps.",
  },
  malformed_response: {
    title: "The model's reply could not be read",
    explanation:
      "The local model returned something that did not match the required " +
      "response format.",
    suggestion: "Asking again usually resolves it.",
  },
  llm_unavailable: {
    title: "The local model is unreachable",
    explanation:
      "No written explanation could be generated. The stored figures are " +
      "unaffected — they were computed by the ratio engine, not by a model.",
    suggestion: "Start Ollama and ask again.",
  },
};

const FALLBACK: RefusalCopy = {
  title: "This question was not answered",
  explanation: "The system declined to answer from this document.",
};

export function describeRefusal(
  reason: string | null | undefined,
): RefusalCopy {
  if (!reason) return FALLBACK;
  return COPY[reason as RefusalReason] ?? FALLBACK;
}

/** Every code this module knows about. Used by its tests. */
export const REFUSAL_REASONS = Object.keys(COPY) as RefusalReason[];
