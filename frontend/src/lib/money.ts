/**
 * Displaying figures without ever making them numbers.
 *
 * Every monetary value and every ratio the backend sends is a `Decimal`
 * serialized as a string. `core/money.py` rejects `float` outright on the way
 * in, for a stated reason: binary drift at the cent level would fail Balance
 * Sheets that genuinely balance. That guarantee is worth exactly nothing if the
 * display layer calls `Number()` on the way out.
 *
 * So everything here is string manipulation - grouping, rounding and sign
 * detection included. There is no arithmetic in this file that a Decimal128
 * value could overflow, because there is no arithmetic on numbers at all.
 *
 * `src/lib/noFloat.test.ts` enforces the rule repository-wide.
 */

import type { Money } from "../types/balanceSheet";

/** Shown where there is no figure. Never a zero, which would be a claim. */
export const NO_VALUE = "—";

/** A plain decimal string: optional sign, digits, optional fractional part. */
const DECIMAL = /^([+-])?(\d+)(?:\.(\d+))?$/;

interface Parts {
  negative: boolean;
  /** Integer digits, at least one. */
  int: string;
  /** Fractional digits exactly as sent, possibly empty. */
  frac: string;
}

/**
 * Split a decimal string into its parts, or `null` if it is not one.
 *
 * Returning `null` rather than guessing is deliberate: a value this cannot
 * read is shown to the user verbatim, because displaying exactly what the
 * backend sent is always safer than displaying a figure we invented.
 */
function parse(value: string): Parts | null {
  const match = DECIMAL.exec(value.trim());
  if (!match) return null;

  const [, sign, int = "0", frac = ""] = match;
  return { negative: sign === "-", int, frac };
}

function isZero(parts: Parts): boolean {
  return /^0*$/.test(parts.int) && /^0*$/.test(parts.frac);
}

/**
 * The successor of each digit below nine.
 *
 * A lookup rather than `Number(d) + 1` so that this file - the one place
 * entitled to touch digits at all - still contains no numeric coercion, and
 * the repository-wide ban in `noFloat.test.ts` can be absolute rather than
 * carve out an exemption that would later be widened.
 */
const NEXT_DIGIT: Readonly<Record<string, string>> = {
  "0": "1",
  "1": "2",
  "2": "3",
  "3": "4",
  "4": "5",
  "5": "6",
  "6": "7",
  "7": "8",
  "8": "9",
};

/** Add one to a string of digits, carrying. May return one digit more. */
function incrementDigits(digits: string): string {
  const out = digits.split("");
  for (let i = out.length - 1; i >= 0; i -= 1) {
    const digit = out[i] ?? "0";
    const next = NEXT_DIGIT[digit];
    if (next !== undefined) {
      out[i] = next;
      return out.join("");
    }
    out[i] = "0"; // was a nine; carry into the next column
  }
  return `1${out.join("")}`;
}

/** Insert thousands separators into a run of integer digits. */
function group(int: string): string {
  return int.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

/**
 * Round a decimal string to `places`, half away from zero.
 *
 * Matches the `ROUND_HALF_UP` the ratio engine uses, so a value re-rounded for
 * display agrees with one the backend rounded itself. An unreadable value is
 * returned untouched.
 */
export function roundDecimalString(value: string, places: number): string {
  const parts = parse(value);
  if (!parts) return value;

  const { int, frac } = parts;
  let negative = parts.negative;
  let resultInt: string;
  let resultFrac: string;

  if (frac.length <= places) {
    resultInt = int;
    resultFrac = frac.padEnd(places, "0");
  } else {
    const keep = frac.slice(0, places);
    // Single digits compare lexically the same way they compare numerically.
    const roundUp = (frac[places] ?? "0") >= "5";
    const combined = int + keep;
    const settled = roundUp ? incrementDigits(combined) : combined;

    resultFrac = places > 0 ? settled.slice(settled.length - places) : "";
    resultInt = places > 0 ? settled.slice(0, settled.length - places) : settled;
    if (resultInt === "") resultInt = "0";
  }

  // -0.001 rounded to 2 places is 0.00, not -0.00.
  if (/^0*$/.test(resultInt) && /^0*$/.test(resultFrac)) negative = false;

  const magnitude = places > 0 ? `${resultInt}.${resultFrac}` : resultInt;
  return negative ? `-${magnitude}` : magnitude;
}

export interface FormatMoneyOptions {
  /**
   * `"parens"` follows the accounting convention the documents themselves use
   * - and that `core/amounts.py` reads back in. `"minus"` where a parenthesis
   * would be ambiguous, such as inside a sentence.
   */
  negativeStyle?: "parens" | "minus";
  /**
   * Drop insignificant trailing zeros from the fraction: `11500.000` reads as
   * `11,500`. Off by default, because for a figure the document printed the
   * precision is itself evidence. Turn it on only for values this system
   * derived, such as the equation tolerance.
   */
  trimTrailingZeros?: boolean;
}

/** Strip trailing zeros, and then a bare point. Pure string work. */
function trimFraction(frac: string): string {
  return frac.replace(/0+$/, "");
}

/**
 * Render a monetary amount for display.
 *
 * The fractional part is passed through exactly as sent: trailing zeros are
 * significant, because the backend chose the precision and this layer is not
 * entitled to second-guess it.
 */
export function formatMoney(
  value: Money | null | undefined,
  options: FormatMoneyOptions = {},
): string {
  if (value === null || value === undefined || value.trim() === "") {
    return NO_VALUE;
  }

  const parts = parse(value);
  if (!parts) return value;

  const negative = parts.negative && !isZero(parts);
  const frac = options.trimTrailingZeros
    ? trimFraction(parts.frac)
    : parts.frac;
  const magnitude = frac ? `${group(parts.int)}.${frac}` : group(parts.int);

  if (!negative) return magnitude;
  return options.negativeStyle === "minus" ? `-${magnitude}` : `(${magnitude})`;
}

/**
 * Render a dimensionless ratio.
 *
 * Rounded for readability - a ratio card showing `1.307692` buries the point -
 * while the exact stored value stays available on `RatioResult.value` for the
 * detail view. A missing ratio is never rendered as zero: `unavailable` means
 * the system could not compute it, which is not the same claim as "it is 0".
 */
export function formatRatio(
  value: Money | null | undefined,
  places = 2,
): string {
  if (value === null || value === undefined || value.trim() === "") {
    return NO_VALUE;
  }
  const parts = parse(value);
  if (!parts) return value;
  return roundDecimalString(value, places);
}

/** Whether an amount is genuinely below zero. Negative zero is not. */
export function isNegative(value: Money | null | undefined): boolean {
  return signOf(value) < 0;
}

/** -1, 0 or 1, without arithmetic. */
export function signOf(value: Money | null | undefined): -1 | 0 | 1 {
  if (value === null || value === undefined) return 0;
  const parts = parse(value);
  if (!parts || isZero(parts)) return 0;
  return parts.negative ? -1 : 1;
}
