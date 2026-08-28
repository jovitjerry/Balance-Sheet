/**
 * Whether every figure in the answer traced back to its context.
 *
 * Shown on every answered turn, not only failures. The check is the reason an
 * answer can be trusted at all, and a guarantee that is only visible when it
 * breaks is one nobody knows they have.
 */

import type { ReactElement } from "react";
import type { Verification } from "../../types/answers";
import { StatusPill } from "../common/StatusPill";
import styles from "./Ask.module.css";

export function VerificationBadge({
  verification,
}: {
  verification: Verification;
}): ReactElement {
  const { passed, figures_verified, figures_unverified, retried } = verification;

  return (
    <div className={styles.verification}>
      <StatusPill tone={passed ? "ok" : "bad"}>
        {passed ? "Figures verified" : "Unverified figures"}
      </StatusPill>

      {figures_verified.length > 0 && (
        <span>
          {figures_verified.length} figure
          {figures_verified.length === 1 ? "" : "s"} traced to the document
        </span>
      )}

      {figures_unverified.length > 0 && (
        <span className={styles.figures}>
          not found in context: {figures_unverified.join(", ")}
        </span>
      )}

      {retried && <span>regenerated once after a failed check</span>}
    </div>
  );
}
