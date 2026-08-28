/**
 * The three ratio statuses must not look alike.
 *
 * The assertion that matters most is the negative one: an `unavailable` ratio
 * must render **no numeral at all**. A dash or a zero standing in for a value
 * the system could not compute is the single most misleading thing this screen
 * could do, and a snapshot test would not notice it changing.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ratio } from "../../test/fixtures";
import { RatioCard } from "./RatioCard";

/** Any digit anywhere in the card's rendered text. */
function digitsIn(container: HTMLElement): string[] {
  return (container.textContent ?? "").match(/\d/g) ?? [];
}

describe("a computed ratio", () => {
  it("shows its value, rounded for reading", () => {
    render(<RatioCard ratio={ratio()} />);
    expect(screen.getByText("1.31")).toBeInTheDocument();
    expect(screen.getByText("Computed")).toBeInTheDocument();
  });

  it("shows the formula it came from", () => {
    render(<RatioCard ratio={ratio()} />);
    expect(
      screen.getByText("Current Assets / Current Liabilities"),
    ).toBeInTheDocument();
  });
});

describe("an unavailable ratio", () => {
  const unavailable = ratio({
    status: "unavailable",
    value: null,
    numerator: null,
    denominator: null,
    reason: "zero_denominator",
  });

  it("renders no numeral, so it can never be read as zero", () => {
    const { container } = render(<RatioCard ratio={unavailable} />);
    expect(digitsIn(container)).toEqual([]);
  });

  it("says so in words instead", () => {
    render(<RatioCard ratio={unavailable} />);
    expect(screen.getByText("Not computed")).toBeInTheDocument();
  });

  it("explains why, from the closed set of reasons", () => {
    render(<RatioCard ratio={unavailable} />);
    expect(screen.getByText(/denominator is zero/i)).toBeInTheDocument();
    // And states the distinction explicitly.
    expect(screen.getByText(/not reported as zero/i)).toBeInTheDocument();
  });

  it("offers no computation detail, because there was no computation", () => {
    render(<RatioCard ratio={unavailable} />);
    expect(screen.queryByText("How this was computed")).not.toBeInTheDocument();
  });
});

describe("a partial ratio", () => {
  const partial = ratio({
    status: "partial",
    value: "1.100000",
    excluded: [
      { canonical_label: null, label: "Sundry balances", value: "50000" },
    ],
    excluded_value: "50000",
  });

  it("names how many lines were left out and their total", () => {
    render(<RatioCard ratio={partial} />);
    expect(screen.getByText(/1 line was left out/i)).toBeInTheDocument();
    // Twice over: once in the bound sentence, once in the excluded list.
    expect(screen.getAllByText("50,000").length).toBeGreaterThan(0);
  });

  it("names the excluded line itself, not just a count", () => {
    render(<RatioCard ratio={partial} />);
    expect(screen.getByText("Sundry balances")).toBeInTheDocument();
  });

  it("states the bound, so the figure is not read as exact", () => {
    render(<RatioCard ratio={partial} />);
    expect(
      screen.getByText(/lies between the figure above and the figure with those included/i),
    ).toBeInTheDocument();
  });
});

describe("nothing is clamped", () => {
  it("keeps negative working capital negative, with its warning", () => {
    render(
      <RatioCard
        ratio={ratio({
          name: "working_capital",
          unit: "currency",
          formula: "Current Assets - Current Liabilities",
          value: "-200000",
          warnings: ["negative_result"],
        })}
      />,
    );

    // The accounting convention, and coloured as a negative.
    const value = screen.getByText("(200,000)");
    expect(value).toBeInTheDocument();
    expect(value).toHaveAttribute("data-negative", "true");
    expect(screen.getByText(/is not clamped/i)).toBeInTheDocument();
  });

  it("surfaces a negative denominator warning", () => {
    render(
      <RatioCard
        ratio={ratio({ value: "-1.5", warnings: ["negative_denominator"] })}
      />,
    );
    expect(screen.getByText(/denominator is negative/i)).toBeInTheDocument();
  });
});
