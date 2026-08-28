/**
 * All three answer statuses arrive as HTTP 200, and none of them is an error.
 *
 * The refusal cases carry the most weight. If a refusal is presented as a
 * failure, a reader learns to distrust the behaviour that keeps answers
 * honest - so these tests check that a refusal states a reason and does not
 * borrow the error styling.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { REFUSAL_REASONS } from "../../lib/refusals";
import { answer, evidence, verification } from "../../test/fixtures";
import { AnswerCard } from "./AnswerCard";

describe("an answered question", () => {
  it("shows the prose", () => {
    render(<AnswerCard answer={answer()} />);
    expect(
      screen.getByText("The current ratio is 1.307692 [R1]."),
    ).toBeInTheDocument();
  });

  it("shows what the model cited and what it was given", () => {
    render(<AnswerCard answer={answer()} />);
    expect(screen.getByText(/^Cited/)).toBeInTheDocument();
    expect(screen.getByText(/^Facts placed in context/)).toBeInTheDocument();
  });

  it("reports the verification result even when it passed", () => {
    render(<AnswerCard answer={answer()} />);
    expect(screen.getByText("Figures verified")).toBeInTheDocument();
    expect(screen.getByText(/1 figure traced to the document/)).toBeInTheDocument();
  });

  it("makes a failed verification visibly different", () => {
    render(
      <AnswerCard
        answer={answer({
          verification: verification({
            passed: false,
            figures_unverified: ["550000"],
            retried: true,
          }),
        })}
      />,
    );
    expect(screen.getByText("Unverified figures")).toBeInTheDocument();
    expect(screen.getByText(/550000/)).toBeInTheDocument();
    expect(screen.getByText(/regenerated once/)).toBeInTheDocument();
  });
});

describe("evidence is rendered as prose and formatted figures", () => {
  it("groups thousands, as every other view does", () => {
    render(
      <AnswerCard
        answer={answer({
          citations: [
            evidence({ id: "F2", kind: "section_total", label: "Total liabilities", value: "1350000" }),
          ],
        })}
      />,
    );
    expect(screen.getByText("1,350,000")).toBeInTheDocument();
    expect(screen.queryByText("1350000")).not.toBeInTheDocument();
  });

  it("names a ratio the way the Ratios tab does, not by its key", () => {
    render(
      <AnswerCard
        answer={answer({
          citations: [
            evidence({ id: "R4", kind: "ratio", label: "debt_to_equity", value: "1.421053" }),
          ],
        })}
      />,
    );
    // The label shares its element with the value, so match on a substring.
    expect(screen.getByText(/Debt to equity/)).toBeInTheDocument();
    expect(screen.queryByText(/debt_to_equity/)).not.toBeInTheDocument();
  });

  it("turns a bare canonical label in the detail line into words", () => {
    render(
      <AnswerCard
        answer={answer({
          citations: [
            evidence({ id: "F7", label: "Long-term borrowings", detail: "long_term_borrowings" }),
          ],
        })}
      />,
    );
    expect(screen.getByText("Long term borrowings")).toBeInTheDocument();
    expect(screen.queryByText("long_term_borrowings")).not.toBeInTheDocument();
  });

  it("leaves a real sentence of detail alone", () => {
    const detail = "Total Liabilities / Total Equity; numerator 1350000";
    render(
      <AnswerCard
        answer={answer({ citations: [evidence({ id: "R4", detail })] })}
      />,
    );
    expect(screen.getByText(detail)).toBeInTheDocument();
  });

  it("shows a negative ratio with a minus and a negative amount in parentheses", () => {
    render(
      <AnswerCard
        answer={answer({
          citations: [
            evidence({ id: "R7", kind: "ratio", label: "working_capital", value: "-50000" }),
            evidence({ id: "F9", kind: "line_item", label: "Accumulated depreciation", value: "-2300" }),
          ],
        })}
      />,
    );
    expect(screen.getByText("-50,000")).toBeInTheDocument();
    expect(screen.getByText("(2,300)")).toBeInTheDocument();
  });
});

describe("a refusal", () => {
  it("is labelled as not answered rather than as an error", () => {
    const { container } = render(
      <AnswerCard
        answer={answer({
          status: "refused",
          answer: null,
          reason: "out_of_scope",
          model: null,
        })}
      />,
    );

    expect(screen.getByText("Not answered")).toBeInTheDocument();
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });

  it.each(REFUSAL_REASONS)("explains the reason %s", (reason) => {
    render(
      <AnswerCard
        answer={answer({ status: "refused", answer: null, reason })}
      />,
    );

    // Every code resolves to a title and an explanation - none renders blank.
    const card = screen.getByRole("article");
    expect(card.textContent?.length ?? 0).toBeGreaterThan(60);
  });

  it("says what a Balance Sheet cannot do, for an out-of-scope question", () => {
    render(
      <AnswerCard
        answer={answer({
          status: "refused",
          answer: null,
          reason: "out_of_scope",
        })}
      />,
    );
    expect(
      screen.getByText(/no revenue, profit or cash flow line/i),
    ).toBeInTheDocument();
  });

  it("presents a withheld answer as the check working", () => {
    render(
      <AnswerCard
        answer={answer({
          status: "refused",
          answer: null,
          reason: "unverifiable_figures",
        })}
      />,
    );
    expect(screen.getByText(/could not be traced back/i)).toBeInTheDocument();
    expect(
      screen.getByText(/grounding check working as intended/i),
    ).toBeInTheDocument();
  });

  it("falls back safely on a reason it does not recognise", () => {
    render(
      <AnswerCard
        answer={answer({
          status: "refused",
          answer: null,
          reason: "something_new_from_the_backend",
        })}
      />,
    );
    expect(screen.getByText("This question was not answered")).toBeInTheDocument();
  });
});

describe("a degraded answer", () => {
  const degraded = answer({
    status: "degraded",
    answer: null,
    model: null,
    reason: "llm_unavailable",
    supporting_facts: [
      evidence({ id: "R1", kind: "ratio", label: "Current ratio", value: "1.307692" }),
    ],
  });

  it("explains why there is no prose", () => {
    render(<AnswerCard answer={degraded} />);
    expect(screen.getByText(/not reachable/i)).toBeInTheDocument();
  });

  it("offers the stored figures, collapsed and counted", () => {
    const { container } = render(<AnswerCard answer={degraded} />);

    // Collapsed by default: a document carries around twenty facts, and
    // expanding them all pushed the question box several screens down.
    const details = container.querySelector("details");
    expect(details).not.toBeNull();
    expect(details).not.toHaveAttribute("open");
    // The count is what tells a reader the figures are there at all.
    expect(screen.getByText("Stored figures (1)")).toBeInTheDocument();
  });

  it("credits the figures to the ratio engine, not the model", () => {
    render(<AnswerCard answer={degraded} />);
    expect(
      screen.getByText(/calculated by the ratio engine, not by a model/i),
    ).toBeInTheDocument();
  });
});
