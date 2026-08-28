/**
 * One answer, in whichever of its three shapes it arrived.
 *
 * All three are HTTP 200 and none of them is an error:
 *
 *   answered   prose, its citations, and the verification result
 *   refused    a stated reason, in neutral colour - this is a correct outcome
 *   degraded   no prose at all, because no model was reachable; the stored
 *              figures are shown instead, since they were computed by the
 *              ratio engine and are unaffected by the model being offline
 */

import type { ReactElement } from "react";
import { describeRefusal } from "../../lib/refusals";
import type { Answer } from "../../types/answers";
import { answerStatusTone, StatusPill } from "../common/StatusPill";
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
        <p className={styles.prose}>{answer.answer}</p>
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
        // Collapsed. A document carries around twenty facts, and expanding all
        // of them by default buried the question box several screens down -
        // the count in the summary says they are there.
        <EvidenceList items={answer.supporting_facts} summary="Stored figures" />
      )}
    </article>
  );
}

/** A refusal, stated plainly and without apology. */
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
