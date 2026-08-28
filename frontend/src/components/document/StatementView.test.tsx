/**
 * The statement must not smooth over what the pipeline was unsure about.
 *
 * A line the model could not map, and a figure that would not parse, are both
 * kept with the document's own wording intact and flagged. Presenting either
 * as though it had been resolved is the one failure nothing downstream can
 * detect.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { document, lineItem } from "../../test/fixtures";
import type { BalanceSheetSection } from "../../types/balanceSheet";
import { StatementView } from "./StatementView";

function section(overrides: Partial<BalanceSheetSection> = {}): BalanceSheetSection {
  return {
    total: "2300000",
    total_label: "TOTAL ASSETS",
    line_items: [],
    ...overrides,
  };
}

function withSections(assets: BalanceSheetSection) {
  return document({
    extracted: {
      entity_name: "Meridian Ltd",
      assets,
      liabilities: section({ total: "1350000", total_label: "TOTAL LIABILITIES" }),
      equity: section({ total: "950000", total_label: "TOTAL EQUITY" }),
    },
  });
}

describe("line items", () => {
  it("shows the label the document printed", () => {
    render(
      <StatementView
        document={withSections(section({ line_items: [lineItem({ label: "Trade Debtors" })] }))}
      />,
    );
    expect(screen.getByText("Trade Debtors")).toBeInTheDocument();
  });

  it("shows the canonical label beside the printed one, never instead of it", () => {
    render(
      <StatementView
        document={withSections(
          section({
            line_items: [
              lineItem({
                label: "Trade Debtors",
                normalization: {
                  canonical_label: "trade_receivables",
                  status: "normalized",
                  method: "llm",
                  taxonomy_version: "1.0.0",
                },
              }),
            ],
          }),
        )}
      />,
    );

    expect(screen.getByText("Trade Debtors")).toBeInTheDocument();
    expect(screen.getByText("Trade receivables")).toBeInTheDocument();
  });

  it("omits the canonical label when it is the same words as the printed one", () => {
    // `cash_and_cash_equivalents` under "Cash and cash equivalents" is the
    // same thing said twice, on nearly every row of a typical sheet.
    render(
      <StatementView
        document={withSections(
          section({
            line_items: [
              lineItem({
                label: "Cash and cash equivalents",
                normalization: {
                  canonical_label: "cash_and_cash_equivalents",
                  status: "normalized",
                  method: "dictionary",
                  taxonomy_version: "1.0.0",
                },
              }),
            ],
          }),
        )}
      />,
    );

    expect(screen.getByText("Cash and cash equivalents")).toBeInTheDocument();
    expect(screen.queryByText("cash and cash equivalents")).not.toBeInTheDocument();
    expect(screen.queryByText("cash_and_cash_equivalents")).not.toBeInTheDocument();
  });

  it("flags a line the model could not map", () => {
    render(
      <StatementView
        document={withSections(
          section({
            line_items: [
              lineItem({
                label: "Sundry balances",
                normalization: {
                  canonical_label: null,
                  status: "needs_review",
                  method: "llm",
                  taxonomy_version: "1.0.0",
                  reason: "no category fits",
                },
              }),
            ],
          }),
        )}
      />,
    );

    expect(screen.getByText("Needs review")).toBeInTheDocument();
  });

  it("marks a line as unmapped when the model was unreachable", () => {
    render(
      <StatementView
        document={withSections(
          section({
            line_items: [
              lineItem({
                normalization: {
                  canonical_label: null,
                  status: "unavailable",
                  method: "unavailable",
                  taxonomy_version: "1.0.0",
                },
              }),
            ],
          }),
        )}
      />,
    );

    expect(screen.getByText("Not mapped")).toBeInTheDocument();
  });

  it("shows the raw string for a figure that would not parse", () => {
    render(
      <StatementView
        document={withSections(
          section({
            line_items: [
              lineItem({
                label: "Contingent item",
                value: null,
                raw: "see note 14",
                status: "unparsed_value",
              }),
            ],
          }),
        )}
      />,
    );

    expect(screen.getByText("Unparsed")).toBeInTheDocument();
    expect(screen.getByText("see note 14")).toBeInTheDocument();
  });

  it("renders a negative line in the document's own convention", () => {
    render(
      <StatementView
        document={withSections(
          section({
            line_items: [
              lineItem({ label: "Accumulated depreciation", value: "-2300", raw: "(2,300)" }),
            ],
          }),
        )}
      />,
    );

    const value = screen.getByText("(2,300)");
    expect(value).toHaveAttribute("data-negative", "true");
  });
});

describe("the printed total", () => {
  it("is shown with the label the document used", () => {
    render(<StatementView document={withSections(section())} />);
    expect(screen.getByText("TOTAL ASSETS")).toBeInTheDocument();
    expect(screen.getByText("2,300,000")).toBeInTheDocument();
  });
});

describe("reconciliation", () => {
  it("is reported as a diagnostic, explicitly not a validation failure", () => {
    render(
      <StatementView
        document={withSections(
          section({ line_items: [lineItem()], reconciliation_difference: "1500" }),
        )}
      />,
    );

    expect(screen.getByText(/diagnostic, not a validation failure/i)).toBeInTheDocument();
  });

  it("is silent when the totals agree", () => {
    render(
      <StatementView
        document={withSections(
          section({ line_items: [lineItem()], reconciliation_difference: "0" }),
        )}
      />,
    );

    expect(screen.queryByText(/diagnostic/i)).not.toBeInTheDocument();
  });
});
