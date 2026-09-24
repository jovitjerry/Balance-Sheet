import type { Grouping } from "./money";
import type { BalanceSheetDocument } from "../types/balanceSheet";
export function documentCurrency(
  document: BalanceSheetDocument,
): string | null {
  return (
    document.extracted?.currency ??
    document.ratios?.currency ??
    document.units?.currency ??
    null
  );
}
const RUPEE = new Set(["inr", "rs", "rs.", "₹", "inr.", "rupees", "rupee"]);
const SYMBOLS: Readonly<Record<string, string>> = {
  inr: "₹",
  usd: "$",
  gbp: "£",
  eur: "€",
  jpy: "¥",
};
export function currencySymbol(code: string | null | undefined): string {
  if (!code) return "";
  const key = code.trim().toLowerCase();
  if (RUPEE.has(key)) return "₹";
  return SYMBOLS[key] ?? code.trim();
}
export function groupingFor(code: string | null | undefined): Grouping {
  if (!code) return "western";
  return RUPEE.has(code.trim().toLowerCase()) ? "indian" : "western";
}
