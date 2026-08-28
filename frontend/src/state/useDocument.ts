/**
 * Loads one document, and guarantees it is the one being asked for.
 *
 * See `useDocument.test.ts` for why the id stamp exists: aborting a request on
 * an id change cannot un-resolve a promise that already settled, so a slow
 * response for the previous document can still arrive and overwrite the
 * current one. Every settled response is checked against the id currently
 * wanted, and dropped if it does not match.
 */

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

  /** The id whose response we are still willing to accept. */
  const wanted = useRef<string | undefined>(documentId);

  useEffect(() => {
    wanted.current = documentId;

    if (!documentId) {
      setState({ kind: "idle" });
      return;
    }

    // Cleared synchronously, before the request is even made, so the previous
    // document is never on screen under the new document's heading - not even
    // for the one frame before the fetch resolves.
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
