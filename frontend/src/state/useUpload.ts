/**
 * Uploading a file and narrating a request that cannot narrate itself.
 *
 * `POST /documents` runs Modules 1-3 inline and returns only when they are all
 * finished. There is no job id, no status endpoint, and nothing to poll -
 * normalization asks the local model about every label it does not already
 * know, so a large sheet legitimately takes minutes behind a single silent
 * request.
 *
 * The stage list below is therefore **the expected order of work, advanced on
 * elapsed time** - not observed server progress. The UI says so in as many
 * words, and an elapsed counter runs alongside it so the estimate is never the
 * only thing a reader has to go on. Inventing a progress bar that claimed to
 * know would be worse than saying nothing.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { isAbort } from "../api/client";
import { uploadDocument } from "../api/documents";
import { checkFile, type FileRejection } from "../lib/upload";
import type { BalanceSheetDocument } from "../types/balanceSheet";

export interface Stage {
  key: string;
  label: string;
  /** Roughly when this stage is expected to begin, in seconds. */
  startsAt: number;
  note?: string;
}

/**
 * The last stage has no successor by design: normalization is the long pole
 * and we cannot tell when it ends, so the display stays there rather than
 * advancing to a "finishing up" it has no evidence for.
 */
export const STAGES: readonly Stage[] = [
  { key: "validate", label: "Validating the file", startsAt: 0 },
  {
    key: "parse",
    label: "Reading the document",
    startsAt: 2,
    note: "Scanned pages are passed through OCR.",
  },
  {
    key: "extract",
    label: "Extracting and normalising line items",
    startsAt: 7,
    note: "Each unfamiliar label is put to the local model. This is the slow part.",
  },
];

export type UploadState =
  | { kind: "idle" }
  | { kind: "rejected"; rejection: FileRejection; filename: string }
  | { kind: "uploading"; filename: string; elapsedMs: number; stageIndex: number }
  | { kind: "failed"; error: unknown; filename: string };

interface UseUploadOptions {
  /** Called once the pipeline returns, whether or not the sheet was accepted. */
  onComplete: (document: BalanceSheetDocument) => void;
}

export function useUpload({ onComplete }: UseUploadOptions) {
  const [state, setState] = useState<UploadState>({ kind: "idle" });
  const controllerRef = useRef<AbortController | null>(null);
  const startedAt = useRef<number>(0);

  // Abort an upload still in flight if the page goes away.
  useEffect(() => () => controllerRef.current?.abort(), []);

  const busy = state.kind === "uploading";

  useEffect(() => {
    if (!busy) return;

    const tick = window.setInterval(() => {
      const elapsedMs = Date.now() - startedAt.current;
      const seconds = elapsedMs / 1000;
      let stageIndex = 0;
      STAGES.forEach((stage, index) => {
        if (seconds >= stage.startsAt) stageIndex = index;
      });

      setState((current) =>
        current.kind === "uploading"
          ? { ...current, elapsedMs, stageIndex }
          : current,
      );
    }, 250);

    return () => window.clearInterval(tick);
  }, [busy]);

  const start = useCallback(
    (file: File) => {
      const rejection = checkFile(file);
      if (rejection) {
        setState({ kind: "rejected", rejection, filename: file.name });
        return;
      }

      const controller = new AbortController();
      controllerRef.current = controller;
      startedAt.current = Date.now();
      setState({
        kind: "uploading",
        filename: file.name,
        elapsedMs: 0,
        stageIndex: 0,
      });

      uploadDocument(file, controller.signal)
        .then((document) => {
          if (controller.signal.aborted) return;
          setState({ kind: "idle" });
          onComplete(document);
        })
        .catch((error: unknown) => {
          // A cancellation is something the user chose; it is not a failure.
          if (isAbort(error)) {
            setState({ kind: "idle" });
            return;
          }
          setState({ kind: "failed", error, filename: file.name });
        });
    },
    [onComplete],
  );

  /**
   * Stops waiting. The server keeps going - it has no idea anyone left - so
   * the document may well be created regardless. The UI says that rather than
   * implying the work was undone.
   */
  const cancel = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setState({ kind: "idle" });
  }, []);

  const reset = useCallback(() => setState({ kind: "idle" }), []);

  return { state, start, cancel, reset };
}
