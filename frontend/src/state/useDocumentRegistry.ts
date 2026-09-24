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
  }
}
function isEntry(value: unknown): value is RegistryEntry {
  if (typeof value !== "object" || value === null) return false;
  const entry = value as Partial<RegistryEntry>;
  return typeof entry.id === "string" && typeof entry.filename === "string";
}
export function useDocumentRegistry() {
  const [entries, setEntries] = useState<RegistryEntry[]>([]);
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
