import type { ReactElement } from "react";
import { formatMoney, formatRatio, isNegative, NO_VALUE } from "../../lib/money";
import type { Money } from "../../types/balanceSheet";
import { useCurrency } from "./CurrencyContext";
interface MoneyValueProps {
  value: Money | null | undefined;
  negativeStyle?: "parens" | "minus";
  trimTrailingZeros?: boolean;
  withSymbol?: boolean;
  className?: string;
}
function withCurrency(text: string, symbol: string): string {
  if (!symbol || text === NO_VALUE) return text;
  if (text.startsWith("(")) return `(${symbol}${text.slice(1)}`;
  if (text.startsWith("-")) return `-${symbol}${text.slice(1)}`;
  return `${symbol}${text}`;
}
export function MoneyValue({
  value,
  negativeStyle = "parens",
  trimTrailingZeros = false,
  withSymbol = false,
  className,
}: MoneyValueProps): ReactElement {
  const { symbol, grouping } = useCurrency();
  const negative = isNegative(value);
  const classes = ["figure", negative ? "figure--negative" : "", className ?? ""]
    .filter(Boolean)
    .join(" ");
  const text = formatMoney(value, { negativeStyle, trimTrailingZeros, grouping });
  return (
    <span className={classes} data-negative={negative || undefined}>
      {withSymbol ? withCurrency(text, symbol) : text}
    </span>
  );
}
interface RatioValueProps {
  value: Money | null | undefined;
  places?: number;
  className?: string;
}
export function RatioValue({
  value,
  places = 2,
  className,
}: RatioValueProps): ReactElement {
  const negative = isNegative(value);
  const classes = ["figure", negative ? "figure--negative" : "", className ?? ""]
    .filter(Boolean)
    .join(" ");
  return (
    <span className={classes} data-negative={negative || undefined}>
      {formatRatio(value, places)}
    </span>
  );
}
export { NO_VALUE };
