/**
 * Shows what went wrong, in the backend's own words.
 *
 * It never invents a message: if the API said something, that is what appears.
 * The added guidance is about what to do next, which is a separate claim.
 */

import type { ReactElement } from "react";
import { describeError } from "../../lib/errors";
import styles from "./ErrorNotice.module.css";

interface ErrorNoticeProps {
  error: unknown;
  /** Heading above the message. */
  title?: string;
  tone?: "bad" | "warn";
  onRetry?: () => void;
}

export function ErrorNotice({
  error,
  title = "Something went wrong",
  tone = "bad",
  onRetry,
}: ErrorNoticeProps): ReactElement {
  const { message, guidance, retryable } = describeError(error);

  return (
    <div className={styles.notice} data-tone={tone} role="alert">
      <p className={styles.title}>{title}</p>
      <p className={styles.message}>{message}</p>
      {guidance && <p className={styles.guidance}>{guidance}</p>}
      {onRetry && retryable && (
        <div className={styles.actions}>
          <button type="button" className="button button--quiet" onClick={onRetry}>
            Try again
          </button>
        </div>
      )}
    </div>
  );
}
