import type { ReactElement } from "react";
import { STAGES } from "../../state/useUpload";
import { Spinner } from "../common/Feedback";
import styles from "./ProcessingStatus.module.css";
interface ProcessingStatusProps {
  filename: string;
  elapsedMs: number;
  stageIndex: number;
  onCancel: () => void;
}
const SLOW_AFTER_MS = 45_000;
export function ProcessingStatus({
  filename,
  elapsedMs,
  stageIndex,
  onCancel,
}: ProcessingStatusProps): ReactElement {
  const seconds = Math.floor(elapsedMs / 1000);
  const slow = elapsedMs > SLOW_AFTER_MS;
  return (
    <section className={styles.panel} aria-live="polite">
      <div className={styles.head}>
        <span className={styles.filename}>{filename}</span>
        <span className={styles.elapsed}>{formatElapsed(seconds)}</span>
      </div>
      <ol className={styles.stages}>
        {STAGES.map((stage, index) => {
          const state =
            index < stageIndex
              ? "done"
              : index === stageIndex
                ? "running"
                : "pending";
          return (
            <li key={stage.key} className={styles.stage} data-state={state}>
              <span className={styles.marker}>
                {state === "done" && "✓"}
                {state === "running" && <Spinner label="in progress" />}
                {state === "pending" && "·"}
              </span>
              <span className={styles.stageLabel}>{stage.label}</span>
              {stage.note && state !== "pending" && (
                <span className={styles.note}>{stage.note}</span>
              )}
            </li>
          );
        })}
      </ol>
      <p className={styles.disclosure}>
        These are the stages in the order the pipeline runs them, advanced on
        elapsed time — the server does not report live progress, so treat them
        as an expectation rather than a measurement. The elapsed time above is
        real.
        {slow && (
          <>
            {" "}
            Normalisation asks the local model about every unfamiliar label, so
            a sheet with many line items genuinely takes minutes.
          </>
        )}
      </p>
      <div className={styles.actions}>
        <button type="button" className="button button--quiet" onClick={onCancel}>
          Stop waiting
        </button>
      </div>
    </section>
  );
}
function formatElapsed(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}
