/**
 * The landing page: choose a file, watch it process, or return to an earlier
 * document.
 */

import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Dropzone } from "../components/upload/Dropzone";
import { ProcessingStatus } from "../components/upload/ProcessingStatus";
import { RecentDocuments } from "../components/upload/RecentDocuments";
import { ErrorNotice } from "../components/common/ErrorNotice";
import { useDocumentRegistry } from "../state/useDocumentRegistry";
import { useUpload } from "../state/useUpload";
import type { BalanceSheetDocument } from "../types/balanceSheet";
import styles from "./UploadPage.module.css";

export default function UploadPage() {
  const navigate = useNavigate();
  const { entries, record, remove } = useDocumentRegistry();

  const onComplete = useCallback(
    (document: BalanceSheetDocument) => {
      record(document);
      // A rejected sheet navigates too. Module 1's verdict and the evidence
      // behind it are the result, and they are on the document - refusing to
      // show them would discard exactly what makes a rejection reviewable.
      if (document._id) navigate(`/documents/${document._id}`);
    },
    [navigate, record],
  );

  const { state, start, cancel } = useUpload({ onComplete });

  return (
    <>
      <section>
        <h2 className="eyebrow">Upload</h2>

        {state.kind === "uploading" ? (
          <ProcessingStatus
            filename={state.filename}
            elapsedMs={state.elapsedMs}
            stageIndex={state.stageIndex}
            onCancel={cancel}
          />
        ) : (
          <Dropzone
            onFile={start}
            rejectionMessage={
              state.kind === "rejected" ? state.rejection.message : undefined
            }
          />
        )}

        {state.kind === "failed" && (
          <div className={styles.failure}>
            <ErrorNotice
              error={state.error}
              title={`Could not process ${state.filename}`}
            />
          </div>
        )}
      </section>

      <RecentDocuments entries={entries} onRemove={remove} />

      <section className="card">
        <h2 className="eyebrow">What this does</h2>
        <div className={styles.prose}>
          <p className={styles.explain}>
            The file is validated by its contents, parsed (with OCR where a page
            is scanned), identified as a Balance Sheet, and checked against the
            accounting equation. Every line item is then extracted and its
            terminology mapped onto a fixed vocabulary by a local model, and
            seven ratios are computed in deterministic Python.
          </p>
          <p className={styles.explain}>
            You can then ask questions about the result. Answers are grounded in
            the stored figures and the document's own text, and every figure in
            an answer is checked against its source before you see it.
          </p>
        </div>
      </section>
    </>
  );
}
