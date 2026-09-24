import type { BalanceSheetDocument } from "../types/balanceSheet";
import { request } from "./client";
export function uploadDocument(
  file: File,
  signal?: AbortSignal,
): Promise<BalanceSheetDocument> {
  const form = new FormData();
  form.append("file", file);
  return request<BalanceSheetDocument>("/documents", {
    method: "POST",
    form,
    signal,
  });
}
export function getDocument(
  documentId: string,
  signal?: AbortSignal,
): Promise<BalanceSheetDocument> {
  return request<BalanceSheetDocument>(
    `/documents/${encodeURIComponent(documentId)}`,
    { signal },
  );
}
