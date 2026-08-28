/**
 * Smoke tests: does each route actually mount?
 *
 * The unit tests above exercise components in isolation, which is exactly the
 * shape of test that misses a crash in composition - a bad import, a hook
 * called in the wrong place, a prop that is undefined only when the real
 * parent supplies it.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const getDocument = vi.hoisted(() => vi.fn());
const getHealth = vi.hoisted(() => vi.fn());
vi.mock("../api/documents", () => ({ getDocument, uploadDocument: vi.fn() }));
vi.mock("../api/meta", () => ({ getHealth, getPipelineStatus: vi.fn() }));

import App from "../App";
import { document as documentFixture, lineItem, ratio } from "../test/fixtures";
import DocumentPage from "./DocumentPage";
import NotFoundPage from "./NotFoundPage";
import UploadPage from "./UploadPage";

function renderAt(path: string) {
  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: <App />,
        children: [
          { index: true, element: <UploadPage /> },
          { path: "documents/:documentId", element: <DocumentPage /> },
          { path: "documents/:documentId/:tab", element: <DocumentPage /> },
          { path: "*", element: <NotFoundPage /> },
        ],
      },
    ],
    { initialEntries: [path] },
  );
  return render(<RouterProvider router={router} />);
}

const analysed = documentFixture({
  extracted: {
    entity_name: "Meridian Ltd",
    period_label: "31 March 2024",
    currency: "GBP",
    assets: {
      total: "2300000",
      total_label: "TOTAL ASSETS",
      line_items: [lineItem()],
    },
    liabilities: { total: "1350000", line_items: [] },
    equity: { total: "950000", line_items: [] },
  },
  ratios: {
    ratios: [ratio(), ratio({ name: "working_capital", unit: "currency", value: "200000" })],
    spec_version: "1.0.0",
    diagnostics: {
      duplicate_canonical_labels: {},
      reconciliation_difference: {},
      normalization_summary: {},
      unclassified: [],
    },
    warnings: [],
    computed_at: "2026-08-28T00:00:00Z",
  },
  equation_check: {
    total_assets: "2300000",
    total_liabilities: "1350000",
    total_equity: "950000",
    expected: "2300000",
    difference: "0",
    tolerance_applied: "1",
    balanced: true,
  },
});

/** Wait for the shell's health indicator to reach a settled state. */
async function settleHealthProbe() {
  await waitFor(() =>
    expect(screen.queryByText(/Checking backend/)).not.toBeInTheDocument(),
  );
}

beforeEach(() => {
  getDocument.mockReset();
  getHealth.mockReset();
  getHealth.mockResolvedValue({ status: "ok", database: "connected" });
  getDocument.mockResolvedValue(analysed);
});

describe("the shell", () => {
  it("renders the upload page at the root", async () => {
    renderAt("/");
    expect(screen.getByText("Drop a Balance Sheet here")).toBeInTheDocument();
    // The shell's health probe resolves after this assertion; awaiting it
    // keeps its state update inside the test rather than leaking an act()
    // warning that would mask a real one later.
    await settleHealthProbe();
  });

  it("reports backend health once it is known", async () => {
    renderAt("/");
    await waitFor(() =>
      expect(screen.getByText("Backend connected")).toBeInTheDocument(),
    );
  });

  it("says so when the backend cannot be reached", async () => {
    getHealth.mockRejectedValue(new Error("down"));
    renderAt("/");
    await waitFor(() =>
      expect(screen.getByText(/Backend unreachable/)).toBeInTheDocument(),
    );
  });

  it("renders a not-found page for an unknown path", async () => {
    renderAt("/nowhere");
    expect(screen.getByText("No such page")).toBeInTheDocument();
    await settleHealthProbe();
  });
});

describe("the document page", () => {
  it("mounts the overview", async () => {
    renderAt("/documents/doc-1");
    await waitFor(() =>
      expect(screen.getByText("Meridian Ltd")).toBeInTheDocument(),
    );
    expect(screen.getByText("Accounting equation")).toBeInTheDocument();
  });

  it("mounts the statement tab", async () => {
    renderAt("/documents/doc-1/statement");
    await waitFor(() =>
      expect(screen.getByText("TOTAL ASSETS")).toBeInTheDocument(),
    );
  });

  it("mounts the ratios tab", async () => {
    renderAt("/documents/doc-1/ratios");
    await waitFor(() =>
      expect(screen.getByText("Current ratio")).toBeInTheDocument(),
    );
    expect(screen.getByText("Working capital")).toBeInTheDocument();
  });

  it("mounts the ask tab", async () => {
    renderAt("/documents/doc-1/ask");
    await waitFor(() =>
      expect(screen.getByText("Ask about this Balance Sheet")).toBeInTheDocument(),
    );
  });

  it("does not print the filename twice when there is no entity name", async () => {
    getDocument.mockResolvedValue(
      documentFixture({
        extracted: {
          entity_name: null,
          assets: { total: "1", line_items: [] },
          liabilities: { total: "1", line_items: [] },
          equity: { total: "0", line_items: [] },
        },
      }),
    );
    renderAt("/documents/doc-1");

    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1, name: "meridian.pdf" }))
        .toBeInTheDocument(),
    );
    // The filename is the heading, so repeating it as a "File" fact beneath
    // says the same thing twice.
    expect(screen.getAllByText("meridian.pdf")).toHaveLength(1);
    expect(screen.queryByText("File")).not.toBeInTheDocument();
  });

  it("still names the file when the entity is named", async () => {
    renderAt("/documents/doc-1");
    await waitFor(() =>
      expect(screen.getByText("Meridian Ltd")).toBeInTheDocument(),
    );
    expect(screen.getByText("meridian.pdf")).toBeInTheDocument();
  });

  it("shows an error when the document cannot be loaded", async () => {
    getDocument.mockRejectedValue(new Error("gone"));
    renderAt("/documents/doc-1");
    await waitFor(() =>
      expect(screen.getByText("Could not load this document")).toBeInTheDocument(),
    );
  });
});

describe("a rejected document", () => {
  const rejected = documentFixture({
    status: "rejected",
    rejection: {
      reason: "equation_unbalanced",
      message: "Assets do not equal liabilities plus equity.",
      at: "2026-08-28T00:00:00Z",
    },
    equation_check: {
      total_assets: "2300000",
      total_liabilities: "1350000",
      total_equity: "900000",
      expected: "2250000",
      difference: "50000",
      tolerance_applied: "1",
      balanced: false,
    },
  });

  it("still shows the verdict and the evidence for it", async () => {
    getDocument.mockResolvedValue(rejected);
    renderAt("/documents/doc-1");

    await waitFor(() =>
      expect(
        screen.getByText("The accounting equation does not balance"),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText("Does not balance")).toBeInTheDocument();
    expect(screen.getByText("50,000")).toBeInTheDocument();
  });

  it("closes off the figures, with the reason stated", async () => {
    getDocument.mockResolvedValue(rejected);
    renderAt("/documents/doc-1/ratios");

    await waitFor(() =>
      expect(screen.getByText("Not available for this document")).toBeInTheDocument(),
    );
    expect(
      screen.getByText(/rejected during validation, so its figures are not shown/i),
    ).toBeInTheDocument();
  });
});
