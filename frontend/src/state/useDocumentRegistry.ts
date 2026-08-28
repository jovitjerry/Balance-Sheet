/**
 * A list of the documents this browser has uploaded.
 *
 * **This is a convenience, never a source of truth.** The backend has no
 * list-documents endpoint, so without it a user would have to keep their own
 * note of every id. What it stores is enough to offer a link and nothing more:
 * every figure ever displayed is fetched live from `GET /documents/{id}`.
 *
 * Consequences that follow from that, and are handled rather than hidden:
 * the list is per-browser, it does not survive clearing site data, and an
 * entry can outlive the document it names - which shows up as a 404 and is
 * reported as "no longer available", never as an empty document.
 */

import { useCallback, useEffect, useState } from "react";
import type { BalanceSheetDocument, DocumentStatus } from "../types/balanceSheet";

const KEY = "bs.documents.v1";
const LIMIT = 25;

export interface RegistryEntry {
  id: string;
  filename: string;
  status: DocumentStatus;
  uploadedAt: string;
  entityName?: string | null;
}

/**
 * Storage can throw outright - Safari's private mode, or a browser configured
 * to block site data - so every access is guarded. A registry that cannot be
 * read is an empty registry, not a broken page.
 */
function read(): RegistryEntry[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isEntry);
  } catch {
    return [];
  }
}

function write(entries: RegistryEntry[]): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(entries.slice(0, LIMIT)));
  } catch {
    // Quota exceeded or storage blocked. The document is still on the server
    // and still reachable by URL; only the convenience list is lost.
  }
}

function isEntry(value: unknown): value is RegistryEntry {
  if (typeof value !== "object" || value === null) return false;
  const entry = value as Partial<RegistryEntry>;
  return typeof entry.id === "string" && typeof entry.filename === "string";
}

export function useDocumentRegistry() {
  const [entries, setEntries] = useState<RegistryEntry[]>([]);

  // Read on mount rather than in a state initialiser: this must not run
  // during server-side rendering or in a test environment without storage.
  useEffect(() => {
    setEntries(read());
  }, []);

  const record = useCallback((document: BalanceSheetDocument) => {
    const id = document._id;
    if (!id) return;

    const entry: RegistryEntry = {
      id,
      filename: document.source.filename,
      status: document.status,
      uploadedAt: document.created_at,
      entityName: document.extracted?.entity_name ?? null,
    };

    setEntries((current) => {
      const next = [entry, ...current.filter((item) => item.id !== id)].slice(
        0,
        LIMIT,
      );
      write(next);
      return next;
    });
  }, []);

  const remove = useCallback((id: string) => {
    setEntries((current) => {
      const next = current.filter((item) => item.id !== id);
      write(next);
      return next;
    });
  }, []);

  return { entries, record, remove };
}
