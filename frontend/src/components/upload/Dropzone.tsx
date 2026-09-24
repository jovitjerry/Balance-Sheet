import { useState, type DragEvent, type ReactElement } from "react";
import { ACCEPT_ATTRIBUTE, formatBytes, MAX_UPLOAD_BYTES } from "../../lib/upload";
import styles from "./Dropzone.module.css";
interface DropzoneProps {
  onFile: (file: File) => void;
  disabled?: boolean;
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
      {}
      <label className={`button ${styles.label}`}>
        <input
          className={styles.input}
          type="file"
          accept={ACCEPT_ATTRIBUTE}
          disabled={disabled}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) onFile(file);
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
