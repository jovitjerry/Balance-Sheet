/** Loading and empty states. */

import type { CSSProperties, ReactElement, ReactNode } from "react";
import styles from "./Feedback.module.css";

export function Spinner({ label }: { label?: string }): ReactElement {
  return (
    <>
      <span className={styles.spinner} aria-hidden="true" />
      {label && <span className="visually-hidden">{label}</span>}
    </>
  );
}

interface EmptyStateProps {
  title: string;
  children?: ReactNode;
}

export function EmptyState({ title, children }: EmptyStateProps): ReactElement {
  return (
    <div className={styles.empty}>
      <p className={styles.emptyTitle}>{title}</p>
      {children}
    </div>
  );
}

/**
 * A placeholder shaped like the content that will replace it.
 *
 * Preferred over a spinner for the document view: the layout does not jump
 * when the data lands, so a reader's eye stays where it was.
 */
export function Skeleton({
  width = "100%",
  height = "1rem",
}: {
  width?: string;
  height?: string;
}): ReactElement {
  const style: CSSProperties = { width, height };
  return <span className={styles.skeleton} style={style} aria-hidden="true" />;
}
