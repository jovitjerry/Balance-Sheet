export const RATIO_ORDER = [
  "current_ratio",
  "quick_ratio",
  "cash_ratio",
  "working_capital",
  "debt_to_equity",
  "debt_ratio",
  "equity_ratio",
] as const;
export const RATIO_LABEL: Record<string, string> = {
  current_ratio: "Current ratio",
  quick_ratio: "Quick ratio",
  cash_ratio: "Cash ratio",
  working_capital: "Working capital",
  debt_to_equity: "Debt to equity",
  debt_ratio: "Debt ratio",
  equity_ratio: "Equity ratio",
};
export const RATIO_GROUP: Record<string, "liquidity" | "leverage"> = {
  current_ratio: "liquidity",
  quick_ratio: "liquidity",
  cash_ratio: "liquidity",
  working_capital: "liquidity",
  debt_to_equity: "leverage",
  debt_ratio: "leverage",
  equity_ratio: "leverage",
};
export const GROUP_LABEL: Record<string, string> = {
  liquidity: "Liquidity",
  leverage: "Leverage and structure",
};
export const RATIO_REASON: Record<string, string> = {
  missing_section_total:
    "A section total this ratio needs was not found on the document.",
  no_classified_inputs:
    "No line item could be classified into the category this ratio needs. " +
    "The lines were extracted; none could be placed.",
  zero_denominator:
    "The denominator is zero, so the ratio has no value. It is not reported " +
    "as zero, because that would be a different claim.",
  not_extracted: "The line items this ratio needs were not extracted.",
  not_representable: "The result could not be represented exactly.",
};
export const RATIO_WARNING: Record<string, string> = {
  unmapped_inputs:
    "Some line items could not be mapped to the canonical vocabulary and were " +
    "left out.",
  unparsed_inputs: "Some printed figures could not be parsed and were left out.",
  negative_numerator: "The numerator is negative.",
  negative_denominator: "The denominator is negative.",
  negative_result:
    "The result is negative. It is reported with its sign and is not clamped.",
};
export function ratioLabel(name: string): string {
  return RATIO_LABEL[name] ?? name.replace(/_/g, " ");
}
export function describeRatioReason(reason: string | null | undefined): string {
  if (!reason) return "";
  return RATIO_REASON[reason] ?? reason.replace(/_/g, " ");
}
export function describeRatioWarning(warning: string): string {
  return RATIO_WARNING[warning] ?? warning.replace(/_/g, " ");
}
export const BASIS_LABEL: Record<string, string> = {
  section_total: "as printed on the document",
  derived_sum: "added up from the line items below",
  composite: "a printed total, adjusted by line items",
};
export interface FormulaParts {
  left: string;
  right: string;
  operator: "÷" | "−";
}
export function splitFormula(formula: string): FormulaParts | null {
  const divide = topLevelIndex(formula, " / ");
  if (divide >= 0) {
    return {
      left: formula.slice(0, divide).trim(),
      right: formula.slice(divide + 3).trim(),
      operator: "÷",
    };
  }
  const subtract = topLevelIndex(formula, " - ");
  if (subtract >= 0) {
    return {
      left: formula.slice(0, subtract).trim(),
      right: formula.slice(subtract + 3).trim(),
      operator: "−",
    };
  }
  return null;
}
function topLevelIndex(formula: string, token: string): number {
  let depth = 0;
  for (let i = 0; i < formula.length; i += 1) {
    const char = formula[i];
    if (char === "(") depth += 1;
    else if (char === ")") depth -= 1;
    else if (depth === 0 && formula.startsWith(token, i)) return i;
  }
  return -1;
}
