/**
 * Choosing a file, by drop or by browse.
 *
 * The visible control is a `<label>` driving a real `<input type="file">`
 * rather than a div with a click handler, so the keyboard and screen-reader
 * behaviour is the browser's own rather than something reimplemented here.
 */

import { useState, type DragEvent, type ReactElement } from "react";
import { ACCEPT_ATTRIBUTE, formatBytes, MAX_UPLOAD_BYTES } from "../../lib/upload";
import styles from "./Dropzone.module.css";

interface DropzoneProps {
  onFile: (file: File) => void;
  disabled?: boolean;
  /** A client-side refusal to show in place, e.g. wrong extension. */
  rejectionMessage?: string;
}

export function Dropzone({
  onFile,
  disabled = false,
  rejectionMessage,
}: DropzoneProps): ReactElement {
  const [dragging, setDragging] = useState(false);

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    if (disabled) return;

    const file = event.dataTransfer.files[0];
    if (file) onFile(file);
  }

  return (
    <div
      className={styles.zone}
      data-dragging={dragging || undefined}
      onDragOver={(event) => {
        event.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      <p className={styles.headline}>Drop a Balance Sheet here</p>
      <p className={styles.hint}>
        PDF or .xlsx, up to {formatBytes(MAX_UPLOAD_BYTES)}. Scanned PDFs are
        read with OCR. One reporting period is analysed.
      </p>

      {/* The input is nested INSIDE the label rather than linked by `for`.
          It has to be visually hidden - a native file input cannot be styled -
          but that leaves its focus ring on a 1px box where nobody can see it.
          As a child, it makes the label match `:focus-within`, so the visible
          control shows the ring instead. As a sibling it could not: the label
          was not an ancestor, so nothing on the page changed when a keyboard
          user tabbed to the app's main entry point. */}
      <label className={`button ${styles.label}`}>
        <input
          className={styles.input}
          type="file"
          accept={ACCEPT_ATTRIBUTE}
          disabled={disabled}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) onFile(file);
            // Clear, so choosing the same file twice fires change both times.
            event.target.value = "";
          }}
        />
        Choose a file
      </label>

      {rejectionMessage && (
        <p className={styles.rejection} role="alert">
          {rejectionMessage}
        </p>
      )}
    </div>
  );
}
