/**
 * The only components allowed to render a figure.
 *
 * Funnelling every amount through here is what makes the no-float rule
 * checkable: `lib/money.ts` is the sole place a decimal string is interpreted,
 * and these are the sole places its output reaches the DOM.
 */

import type { ReactElement } from "react";
import { formatMoney, formatRatio, isNegative, NO_VALUE } from "../../lib/money";
import type { Money } from "../../types/balanceSheet";

interface MoneyValueProps {
  value: Money | null | undefined;
  /**
   * `"parens"` (the default) follows the accounting convention the documents
   * themselves print. `"minus"` reads better inside a sentence.
   */
  negativeStyle?: "parens" | "minus";
  /** See `FormatMoneyOptions`. For derived values only, never printed ones. */
  trimTrailingZeros?: boolean;
  className?: string;
}

/** A monetary amount. Negative amounts keep their sign and are coloured. */
export function MoneyValue({
  value,
  negativeStyle = "parens",
  trimTrailingZeros = false,
  className,
}: MoneyValueProps): ReactElement {
  const negative = isNegative(value);
  const classes = ["figure", negative ? "figure--negative" : "", className ?? ""]
    .filter(Boolean)
    .join(" ");

  return (
    <span className={classes} data-negative={negative || undefined}>
      {formatMoney(value, { negativeStyle, trimTrailingZeros })}
    </span>
  );
}

interface RatioValueProps {
  value: Money | null | undefined;
  places?: number;
  className?: string;
}

/**
 * A dimensionless ratio.
 *
 * A missing value renders as an em dash and never as zero - `unavailable`
 * means the system could not compute the ratio, which is a different claim
 * from "the ratio is 0".
 */
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
