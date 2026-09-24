import type { ReactElement } from "react";
import { Link } from "react-router-dom";
import type { RegistryEntry } from "../../state/useDocumentRegistry";
import {
  DOCUMENT_STATUS_LABEL,
  documentStatusTone,
  StatusPill,
} from "../common/StatusPill";
import styles from "./RecentDocuments.module.css";
interface RecentDocumentsProps {
  entries: RegistryEntry[];
  onRemove: (id: string) => void;
}
export function RecentDocuments({
  entries,
  onRemove,
}: RecentDocumentsProps): ReactElement | null {
  if (entries.length === 0) return null;
  return (
    <section className="card">
      <h2 className="eyebrow">Recent documents</h2>
      <ul className={styles.list}>
        {entries.map((entry) => (
          <li key={entry.id} className={styles.item}>
            <div className={styles.row}>
              <Link to={`/documents/${entry.id}`} className={styles.link}>
                <span className={styles.filename}>
                  {entry.entityName || entry.filename}
                </span>
                <span className={styles.meta}>
                  {entry.entityName ? `${entry.filename} · ` : ""}
                  {formatWhen(entry.uploadedAt)}
                </span>
              </Link>
              <StatusPill tone={documentStatusTone(entry.status)}>
                {DOCUMENT_STATUS_LABEL[entry.status]}
              </StatusPill>
              <button
                type="button"
                className={styles.remove}
                onClick={() => onRemove(entry.id)}
                aria-label={`Remove ${entry.filename} from this list`}
              >
                Remove
              </button>
            </div>
          </li>
        ))}
      </ul>
      <p className={styles.note}>
        Kept in this browser only — the API has no document list. Removing an
        entry forgets the link; it does not delete anything on the server.
      </p>
    </section>
  );
}
function formatWhen(iso: string): string {
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return iso;
  return when.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
