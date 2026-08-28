/** A small labelled badge, used for every status vocabulary in the app. */

import type { ReactElement, ReactNode } from "react";
import type { AnswerStatus } from "../../types/answers";
import type { DocumentStatus, RatioStatus } from "../../types/balanceSheet";
import styles from "./StatusPill.module.css";

export type Tone = "ok" | "warn" | "bad" | "neutral" | "accent";

interface StatusPillProps {
  tone: Tone;
  children: ReactNode;
  title?: string;
}

export function StatusPill({
  tone,
  children,
  title,
}: StatusPillProps): ReactElement {
  return (
    <span className={`${styles.pill} ${styles[tone]}`} title={title}>
      {children}
    </span>
  );
}

/**
 * How far a document got.
 *
 * `rejected` is amber rather than red: the document was read, understood and
 * judged, and the verdict was recorded as evidence. That is the system working,
 * not failing. `failed` - where processing itself broke - is the red one.
 */
export function documentStatusTone(status: DocumentStatus): Tone {
  switch (status) {
    case "analyzed":
    case "extracted":
    case "validated":
      return "ok";
    case "rejected":
      return "warn";
    case "failed":
      return "bad";
    default:
      return "neutral";
  }
}

export const DOCUMENT_STATUS_LABEL: Record<DocumentStatus, string> = {
  uploaded: "Uploaded",
  parsed: "Parsed",
  validated: "Validated",
  extracted: "Extracted",
  analyzed: "Analysed",
  rejected: "Rejected",
  failed: "Failed",
};

export function ratioStatusTone(status: RatioStatus): Tone {
  switch (status) {
    case "ok":
      return "ok";
    case "partial":
      return "warn";
    case "unavailable":
      return "neutral";
  }
}

export const RATIO_STATUS_LABEL: Record<RatioStatus, string> = {
  ok: "Computed",
  partial: "Partial",
  unavailable: "Unavailable",
};

/**
 * A refusal is neutral, never red. Declining to answer a question this
 * document cannot support is a correct outcome, and colouring it as an error
 * would teach a reader to distrust the one behaviour that keeps answers honest.
 */
export function answerStatusTone(status: AnswerStatus): Tone {
  switch (status) {
    case "answered":
      return "ok";
    case "refused":
      return "neutral";
    case "degraded":
      return "warn";
  }
}
