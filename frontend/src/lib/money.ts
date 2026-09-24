import type { Money } from "../types/balanceSheet";
export const NO_VALUE = "—";
const DECIMAL = /^([+-])?(\d+)(?:\.(\d+))?$/;
interface Parts {
  negative: boolean;
  int: string;
  frac: string;
}
function parse(value: string): Parts | null {
  const match = DECIMAL.exec(value.trim());
  if (!match) return null;
  const [, sign, int = "0", frac = ""] = match;
  return { negative: sign === "-", int, frac };
}
function isZero(parts: Parts): boolean {
  return /^0*$/.test(parts.int) && /^0*$/.test(parts.frac);
}
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
function incrementDigits(digits: string): string {
  const out = digits.split("");
  for (let i = out.length - 1; i >= 0; i -= 1) {
    const digit = out[i] ?? "0";
    const next = NEXT_DIGIT[digit];
    if (next !== undefined) {
      out[i] = next;
      return out.join("");
    }
    out[i] = "0"; 
  }
  return `1${out.join("")}`;
}
export type Grouping = "western" | "indian";
function group(int: string, grouping: Grouping = "western"): string {
  if (grouping !== "indian") return int.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  if (int.length <= 3) return int;
  const head = int.slice(0, int.length - 3);
  const tail = int.slice(int.length - 3);
  return `${head.replace(/\B(?=(\d{2})+(?!\d))/g, ",")},${tail}`;
}
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
    const roundUp = (frac[places] ?? "0") >= "5";
    const combined = int + keep;
    const settled = roundUp ? incrementDigits(combined) : combined;
    resultFrac = places > 0 ? settled.slice(settled.length - places) : "";
    resultInt = places > 0 ? settled.slice(0, settled.length - places) : settled;
    if (resultInt === "") resultInt = "0";
  }
  if (/^0*$/.test(resultInt) && /^0*$/.test(resultFrac)) negative = false;
  const magnitude = places > 0 ? `${resultInt}.${resultFrac}` : resultInt;
  return negative ? `-${magnitude}` : magnitude;
}
export interface FormatMoneyOptions {
  negativeStyle?: "parens" | "minus";
  trimTrailingZeros?: boolean;
  grouping?: Grouping;
}
function trimFraction(frac: string): string {
  return frac.replace(/0+$/, "");
}
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
  const int = group(parts.int, options.grouping);
  const magnitude = frac ? `${int}.${frac}` : int;
  if (!negative) return magnitude;
  return options.negativeStyle === "minus" ? `-${magnitude}` : `(${magnitude})`;
}
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
export function regroupFigures(text: string, grouping: Grouping): string {
  if (grouping !== "indian") return text;
  return text.replace(/(?<![\w,.])\d[\d,]*(?![\w,])/g, (match) => {
    const bare = match.replace(/,/g, "");
    if (!/^\d+$/.test(bare)) return match;
    if (!match.includes(",") && bare.length < 5) return match;
    return group(bare, "indian");
  });
}
export function isNegative(value: Money | null | undefined): boolean {
  return signOf(value) < 0;
}
export function signOf(value: Money | null | undefined): -1 | 0 | 1 {
  if (value === null || value === undefined) return 0;
  const parts = parse(value);
  if (!parts || isZero(parts)) return 0;
  return parts.negative ? -1 : 1;
}
