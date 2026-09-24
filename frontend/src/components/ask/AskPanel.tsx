import type { ReactElement } from "react";
import { useConversation } from "../../state/useConversation";
import { ErrorNotice } from "../common/ErrorNotice";
import { EmptyState, Spinner } from "../common/Feedback";
import { AnswerCard } from "./AnswerCard";
import { QuestionInput } from "./QuestionInput";
import styles from "./Ask.module.css";
export function AskPanel({
  documentId,
}: {
  documentId: string;
}): ReactElement {
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
      <QuestionInput onAsk={ask} busy={pending !== null} />
    </div>
  );
}
