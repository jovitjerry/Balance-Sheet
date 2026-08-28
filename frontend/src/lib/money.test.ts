/**
 * The most safety-critical tests in the frontend.
 *
 * Every figure the backend sends is a `Decimal` serialized as a string,
 * precisely so it never passes through an IEEE double. These tests exist to
 * prove that the display layer honours that: a value that `Number()` would
 * corrupt must survive formatting byte-for-byte.
 */

import { describe, expect, it } from "vitest";
import {
  formatMoney,
  formatRatio,
  isNegative,
  roundDecimalString,
  signOf,
} from "./money";

describe("formatMoney", () => {
  it("groups thousands", () => {
    expect(formatMoney("2300")).toBe("2,300");
    expect(formatMoney("1000000")).toBe("1,000,000");
    expect(formatMoney("123")).toBe("123");
    expect(formatMoney("1234567890")).toBe("1,234,567,890");
  });

  it("renders negatives in the accounting convention the document uses", () => {
    expect(formatMoney("-2300")).toBe("(2,300)");
    expect(formatMoney("-1234.50")).toBe("(1,234.50)");
  });

  it("can render negatives with a minus sign instead", () => {
    expect(formatMoney("-2300", { negativeStyle: "minus" })).toBe("-2,300");
  });

  it("leaves the fractional part exactly as sent", () => {
    // Trailing zeros are significant: the backend chose to send "1234.50".
    expect(formatMoney("1234.50")).toBe("1,234.50");
    expect(formatMoney("0.000001")).toBe("0.000001");
    expect(formatMoney("0.10")).toBe("0.10");
  });

  it("treats negative zero as zero", () => {
    expect(formatMoney("-0")).toBe("0");
    expect(formatMoney("-0.00")).toBe("0.00");
  });

  it("survives a value that a JavaScript number would corrupt", () => {
    // Number("9007199254740993.01") === 9007199254740992 - the cent is lost
    // and so is the odd unit. String handling keeps every digit.
    expect(formatMoney("9007199254740993.01")).toBe("9,007,199,254,740,993.01");
  });

  it("handles the full 34 significant digits Decimal128 allows", () => {
    expect(formatMoney("1234567890123456789012345678901234")).toBe(
      "1,234,567,890,123,456,789,012,345,678,901,234",
    );
  });

  it("can drop insignificant trailing zeros from a derived figure", () => {
    // The equation tolerance arrives with the scale of the percentage that
    // produced it: "11500.000" beside a column of whole amounts reads wrong.
    expect(formatMoney("11500.000", { trimTrailingZeros: true })).toBe("11,500");
    expect(formatMoney("1234.50", { trimTrailingZeros: true })).toBe("1,234.5");
    expect(formatMoney("0.000", { trimTrailingZeros: true })).toBe("0");
  });

  it("keeps significant digits when trimming", () => {
    expect(formatMoney("1234.05", { trimTrailingZeros: true })).toBe("1,234.05");
    expect(formatMoney("0.000001", { trimTrailingZeros: true })).toBe("0.000001");
  });

  it("does not trim by default - a printed precision is evidence", () => {
    expect(formatMoney("1234.50")).toBe("1,234.50");
  });

  it("renders an em dash for a missing value, never a zero", () => {
    expect(formatMoney(null)).toBe("—");
    expect(formatMoney(undefined)).toBe("—");
    expect(formatMoney("")).toBe("—");
  });

  it("returns an unrecognised string untouched rather than mangling it", () => {
    // Better to show exactly what the backend sent than to invent a figure.
    expect(formatMoney("1E+2")).toBe("1E+2");
    expect(formatMoney("not a number")).toBe("not a number");
  });
});

describe("roundDecimalString", () => {
  it("rounds half up, matching the backend's ROUND_HALF_UP", () => {
    expect(roundDecimalString("1.305", 2)).toBe("1.31");
    expect(roundDecimalString("1.304", 2)).toBe("1.30");
    expect(roundDecimalString("1.307692", 2)).toBe("1.31");
    expect(roundDecimalString("0.192308", 2)).toBe("0.19");
  });

  it("rounds the magnitude, so a negative half goes away from zero", () => {
    expect(roundDecimalString("-1.305", 2)).toBe("-1.31");
    expect(roundDecimalString("-1.304", 2)).toBe("-1.30");
  });

  it("propagates a carry across the decimal point", () => {
    expect(roundDecimalString("0.999", 2)).toBe("1.00");
    expect(roundDecimalString("9.999", 2)).toBe("10.00");
    expect(roundDecimalString("99.999", 2)).toBe("100.00");
    expect(roundDecimalString("-9.999", 2)).toBe("-10.00");
  });

  it("pads a short fraction out to the requested places", () => {
    expect(roundDecimalString("1", 2)).toBe("1.00");
    expect(roundDecimalString("1.5", 2)).toBe("1.50");
  });

  it("can round to zero decimal places", () => {
    expect(roundDecimalString("1.5", 0)).toBe("2");
    expect(roundDecimalString("1.4", 0)).toBe("1");
  });

  it("does not lose precision on a value larger than 2^53", () => {
    expect(roundDecimalString("9007199254740993.015", 2)).toBe(
      "9007199254740993.02",
    );
  });
});

describe("formatRatio", () => {
  it("rounds a stored ratio to a readable precision", () => {
    expect(formatRatio("1.307692")).toBe("1.31");
    expect(formatRatio("0.769231")).toBe("0.77");
    expect(formatRatio("0.192308")).toBe("0.19");
    expect(formatRatio("1.421053")).toBe("1.42");
  });

  it("honours a requested precision", () => {
    expect(formatRatio("1.307692", 4)).toBe("1.3077");
  });

  it("never turns a missing ratio into zero", () => {
    expect(formatRatio(null)).toBe("—");
    expect(formatRatio(undefined)).toBe("—");
  });

  it("keeps a negative ratio negative", () => {
    // Negative equity produces one. Nothing is clamped.
    expect(formatRatio("-0.250000")).toBe("-0.25");
  });
});

describe("isNegative", () => {
  it("identifies genuinely negative amounts", () => {
    expect(isNegative("-1")).toBe(true);
    expect(isNegative("-0.01")).toBe(true);
  });

  it("does not treat zero or negative zero as negative", () => {
    expect(isNegative("0")).toBe(false);
    expect(isNegative("-0")).toBe(false);
    expect(isNegative("-0.00")).toBe(false);
  });

  it("is false for positives and for nothing at all", () => {
    expect(isNegative("1")).toBe(false);
    expect(isNegative(null)).toBe(false);
    expect(isNegative(undefined)).toBe(false);
  });
});

describe("signOf", () => {
  it("reports the sign without arithmetic", () => {
    expect(signOf("-2300")).toBe(-1);
    expect(signOf("2300")).toBe(1);
    expect(signOf("0")).toBe(0);
    expect(signOf("-0.000")).toBe(0);
    expect(signOf(null)).toBe(0);
  });
});
