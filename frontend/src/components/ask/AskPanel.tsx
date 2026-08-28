/**
 * The question thread for one document.
 *
 * The suggestions are built from what this document actually holds - a ratio
 * it computed, a line item it extracted - rather than from a fixed list, so a
 * starter question never asks about something that is not there.
 */

import type { ReactElement } from "react";
import { ratioLabel } from "../../lib/ratios";
import { useConversation } from "../../state/useConversation";
import type { BalanceSheetDocument } from "../../types/balanceSheet";
import { ErrorNotice } from "../common/ErrorNotice";
import { EmptyState, Spinner } from "../common/Feedback";
import { AnswerCard } from "./AnswerCard";
import { QuestionInput } from "./QuestionInput";
import styles from "./Ask.module.css";

interface AskPanelProps {
  documentId: string;
  document: BalanceSheetDocument;
}

export function AskPanel({ documentId, document }: AskPanelProps): ReactElement {
  const { exchanges, pending, error, ask } = useConversation(documentId);

  return (
    <div className={styles.panel}>
      {exchanges.length === 0 && !pending && (
        <EmptyState title="Ask about this Balance Sheet">
          <p>
            Answers come from the figures already computed and from the
            document's own text. The model explains them; it never calculates,
            and every figure in a reply is checked against its source first.
          </p>
        </EmptyState>
      )}

      <div className={styles.thread}>
        {exchanges.map((exchange, index) => (
          <div key={`${exchange.question}-${index}`}>
            <p className={styles.question}>
              <span className={styles.questionMark}>Q</span>
              <span className={styles.questionText}>{exchange.question}</span>
            </p>
            <AnswerCard answer={exchange.answer} />
          </div>
        ))}

        {pending && (
          <div>
            <p className={styles.question}>
              <span className={styles.questionMark}>Q</span>
              <span className={styles.questionText}>{pending}</span>
            </p>
            <p className={styles.pending}>
              <Spinner label="Thinking" />
              Retrieving and answering — the local model takes a few seconds.
            </p>
          </div>
        )}
      </div>

      {error !== null && (
        <ErrorNotice error={error} title="That question could not be sent" />
      )}

      <QuestionInput
        onAsk={ask}
        busy={pending !== null}
        suggestions={suggestionsFor(document)}
      />
    </div>
  );
}

/** Starters drawn from this document, so none of them asks about nothing. */
function suggestionsFor(document: BalanceSheetDocument): string[] {
  const suggestions: string[] = [];

  const computed = document.ratios?.ratios.find(
    (ratio) => ratio.status !== "unavailable",
  );
  if (computed) {
    suggestions.push(`What does the ${ratioLabel(computed.name).toLowerCase()} tell me?`);
  }

  const item = document.extracted?.assets.line_items.find(
    (line) => line.value !== null && line.value !== undefined,
  );
  if (item) suggestions.push(`How much is ${item.label.toLowerCase()}?`);

  suggestions.push("What is this company's asset base made up of?");

  return suggestions.slice(0, 3);
}
