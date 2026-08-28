import { describe, expect, it } from "vitest";
import { humanizeIdentifier, isIdentifier, sameConcept } from "./labels";

describe("humanizeIdentifier", () => {
  it("turns a canonical label into words", () => {
    expect(humanizeIdentifier("cash_and_cash_equivalents")).toBe(
      "Cash and cash equivalents",
    );
    expect(humanizeIdentifier("long_term_borrowings")).toBe(
      "Long term borrowings",
    );
  });

  it("leaves a single word alone but capitalised", () => {
    expect(humanizeIdentifier("inventory")).toBe("Inventory");
  });

  it("returns an empty identifier unchanged rather than throwing", () => {
    expect(humanizeIdentifier("")).toBe("");
  });
});

describe("isIdentifier", () => {
  it("recognises a snake_case key", () => {
    expect(isIdentifier("trade_payables")).toBe(true);
    expect(isIdentifier("inventory")).toBe(true);
  });

  it("does not mistake prose for a key", () => {
    expect(isIdentifier("Cash and cash equivalents")).toBe(false);
    expect(isIdentifier("Total Liabilities / Total Equity; numerator 1")).toBe(
      false,
    );
    expect(isIdentifier("Trade Debtors")).toBe(false);
  });
});

describe("sameConcept", () => {
  it("sees through case, underscores and punctuation", () => {
    expect(sameConcept("cash_and_cash_equivalents", "Cash and cash equivalents")).toBe(
      true,
    );
    expect(sameConcept("trade_payables", "Trade Payables")).toBe(true);
    expect(sameConcept("inventory", "Inventories")).toBe(false);
  });

  it("keeps genuinely different wordings apart", () => {
    // The whole point of normalization: these must stay distinguishable.
    expect(sameConcept("trade_receivables", "Trade Debtors")).toBe(false);
  });

  it("is false when either side is missing", () => {
    expect(sameConcept(null, "Inventory")).toBe(false);
    expect(sameConcept("inventory", undefined)).toBe(false);
  });
});
