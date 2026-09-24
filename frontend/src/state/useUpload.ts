import { useCallback, useEffect, useRef, useState } from "react";
import { isAbort } from "../api/client";
import { uploadDocument } from "../api/documents";
import { checkFile, type FileRejection } from "../lib/upload";
import type { BalanceSheetDocument } from "../types/balanceSheet";
export interface Stage {
  key: string;
  label: string;
  startsAt: number;
  note?: string;
}
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
  onComplete: (document: BalanceSheetDocument) => void;
}
export function useUpload({ onComplete }: UseUploadOptions) {
  const [state, setState] = useState<UploadState>({ kind: "idle" });
  const controllerRef = useRef<AbortController | null>(null);
  const startedAt = useRef<number>(0);
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
          if (isAbort(error)) {
            setState({ kind: "idle" });
            return;
          }
          setState({ kind: "failed", error, filename: file.name });
        });
    },
    [onComplete],
  );
  const cancel = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setState({ kind: "idle" });
  }, []);
  const reset = useCallback(() => setState({ kind: "idle" }), []);
  return { state, start, cancel, reset };
}
