/**
 * Fixtures shaped like real responses.
 *
 * The figures are the Meridian sheet used throughout the backend's own tests
 * and benchmarks, so a number appearing here can be checked against a value
 * the backend actually produces.
 */

import type { Answer, Evidence, Verification } from "../types/answers";
import type {
  BalanceSheetDocument,
  LineItem,
  RatioResult,
} from "../types/balanceSheet";

export function lineItem(overrides: Partial<LineItem> = {}): LineItem {
  return {
    label: "Inventory",
    value: "350000",
    raw: "350,000",
    subsection: "current",
    status: "extracted",
    normalization: {
      canonical_label: "inventory",
      status: "normalized",
      method: "llm",
      confidence: 0.95,
      taxonomy_version: "1.0.0",
      model: "qwen3:8b",
    },
    ...overrides,
  };
}

export function ratio(overrides: Partial<RatioResult> = {}): RatioResult {
  return {
    name: "current_ratio",
    formula: "Current Assets / Current Liabilities",
    definition: "Whether assets expected to become cash within a year cover…",
    unit: "ratio",
    status: "ok",
    value: "1.307692",
    numerator: "850000",
    denominator: "650000",
    numerator_basis: "derived_sum",
    denominator_basis: "derived_sum",
    numerator_inputs: [],
    denominator_inputs: [],
    excluded: [],
    warnings: [],
    ...overrides,
  };
}

export function evidence(overrides: Partial<Evidence> = {}): Evidence {
  return {
    id: "F1",
    kind: "line_item",
    label: "Inventory",
    value: "350,000",
    ...overrides,
  };
}

export function verification(
  overrides: Partial<Verification> = {},
): Verification {
  return {
    passed: true,
    figures_verified: ["1.307692"],
    figures_unverified: [],
    retried: false,
    ...overrides,
  };
}

export function answer(overrides: Partial<Answer> = {}): Answer {
  return {
    document_id: "doc-1",
    question: "What is the current ratio?",
    answer: "The current ratio is 1.307692 [R1].",
    status: "answered",
    route: "structured",
    supporting_facts: [evidence()],
    citations: [evidence({ id: "R1", kind: "ratio", label: "Current ratio" })],
    verification: verification(),
    reason: null,
    model: "qwen3:8b",
    spec_version: "1.0.0",
    created_at: "2026-08-28T00:00:00Z",
    ...overrides,
  };
}

export function document(
  overrides: Partial<BalanceSheetDocument> = {},
): BalanceSheetDocument {
  return {
    _id: "doc-1",
    status: "analyzed",
    source: {
      filename: "meridian.pdf",
      content_type: "application/pdf",
      size_bytes: 12345,
      sha256: "0".repeat(64),
      ref: {
        backend: "local",
        key: "ab/cd",
        size_bytes: 12345,
        content_type: "application/pdf",
      },
    },
    errors: [],
    created_at: "2026-08-28T00:00:00Z",
    updated_at: "2026-08-28T00:00:00Z",
    ...overrides,
  };
}
