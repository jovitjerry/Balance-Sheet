import type { ReactElement } from "react";
import { describeError } from "../../lib/errors";
import styles from "./ErrorNotice.module.css";
interface ErrorNoticeProps {
  error: unknown;
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
