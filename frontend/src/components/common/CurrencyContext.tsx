import { createContext, use, type ReactElement, type ReactNode } from "react";
import { currencySymbol, documentCurrency, groupingFor } from "../../lib/currency";
import type { Grouping } from "../../lib/money";
import type { BalanceSheetDocument } from "../../types/balanceSheet";
export interface CurrencyInfo {
  code: string | null;
  symbol: string;
  grouping: Grouping;
}
const NONE: CurrencyInfo = { code: null, symbol: "", grouping: "western" };
const CurrencyContext = createContext<CurrencyInfo>(NONE);
export function CurrencyProvider({
  document,
  children,
}: {
  document: BalanceSheetDocument;
  children: ReactNode;
}): ReactElement {
  const code = documentCurrency(document);
  const value: CurrencyInfo = {
    code,
    symbol: currencySymbol(code),
    grouping: groupingFor(code),
  };
  return <CurrencyContext value={value}>{children}</CurrencyContext>;
}
export function useCurrency(): CurrencyInfo {
  return use(CurrencyContext);
}
