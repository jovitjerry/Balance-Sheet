import { useCallback, useEffect, useRef, useState } from "react";
import { isAbort } from "../api/client";
import { getDocument } from "../api/documents";
import type { BalanceSheetDocument } from "../types/balanceSheet";
export type DocumentState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; document: BalanceSheetDocument }
  | { kind: "error"; error: unknown };
export function useDocument(documentId: string | undefined) {
  const [state, setState] = useState<DocumentState>(
    documentId ? { kind: "loading" } : { kind: "idle" },
  );
  const [reloadToken, setReloadToken] = useState(0);
  const wanted = useRef<string | undefined>(documentId);
  useEffect(() => {
    wanted.current = documentId;
    if (!documentId) {
      setState({ kind: "idle" });
      return;
    }
    setState({ kind: "loading" });
    const controller = new AbortController();
    getDocument(documentId, controller.signal)
      .then((document) => {
        if (wanted.current !== documentId) return;
        setState({ kind: "ready", document });
      })
      .catch((error: unknown) => {
        if (isAbort(error)) return;
        if (wanted.current !== documentId) return;
        setState({ kind: "error", error });
      });
    return () => controller.abort();
  }, [documentId, reloadToken]);
  const reload = useCallback(() => setReloadToken((n) => n + 1), []);
  return { state, reload };
}
