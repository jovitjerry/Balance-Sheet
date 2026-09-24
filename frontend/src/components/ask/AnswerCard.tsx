import type { ReactElement } from "react";
import { describeRefusal } from "../../lib/refusals";
import type { Answer } from "../../types/answers";
import { answerStatusTone, StatusPill } from "../common/StatusPill";
import { AnswerProse } from "./AnswerProse";
import { EvidenceList } from "./EvidenceList";
import { VerificationBadge } from "./VerificationBadge";
import styles from "./Ask.module.css";
const STATUS_LABEL: Record<Answer["status"], string> = {
  answered: "Answered",
  refused: "Not answered",
  degraded: "Figures only",
};
export function AnswerCard({ answer }: { answer: Answer }): ReactElement {
  return (
    <article className={styles.answer} data-status={answer.status}>
      <div className={styles.head}>
        <StatusPill tone={answerStatusTone(answer.status)}>
          {STATUS_LABEL[answer.status]}
        </StatusPill>
        {answer.model && <span className={styles.model}>{answer.model}</span>}
      </div>
      {answer.status === "refused" ? (
        <RefusalNotice reason={answer.reason} />
      ) : answer.status === "degraded" ? (
        <DegradedNotice />
      ) : (
        <AnswerProse text={answer.answer ?? ""} />
      )}
      {answer.status === "answered" && (
        <>
          <EvidenceList items={answer.citations} summary="Cited" />
          <EvidenceList
            items={answer.supporting_facts}
            summary="Facts placed in context"
          />
          <VerificationBadge verification={answer.verification} />
        </>
      )}
      {answer.status === "degraded" && (
        <EvidenceList items={answer.supporting_facts} summary="Stored figures" />
      )}
    </article>
  );
}
function RefusalNotice({ reason }: { reason: string | null | undefined }) {
  const { title, explanation, suggestion } = describeRefusal(reason);
  return (
    <>
      <p className={styles.refusalTitle}>{title}</p>
      <p className={styles.refusalBody}>{explanation}</p>
      {suggestion && <p className={styles.refusalSuggestion}>{suggestion}</p>}
    </>
  );
}
function DegradedNotice() {
  return (
    <p className={styles.degradedNote}>
      The local language model is not reachable, so there is no written
      explanation. The figures below are unaffected — they were calculated by
      the ratio engine, not by a model.
    </p>
  );
}
