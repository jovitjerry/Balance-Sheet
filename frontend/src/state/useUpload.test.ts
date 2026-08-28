/**
 * The upload outcome that is easiest to get wrong.
 *
 * `POST /documents` answers **201 with `status: "rejected"`** when a sheet was
 * read and understood but failed validation. That is not an error - the
 * rejection and the evidence for it are the result, and the record is kept for
 * audit. Treating it as a failure would throw away exactly what makes a refusal
 * reviewable.
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";

const uploadDocument = vi.hoisted(() => vi.fn());
vi.mock("../api/documents", () => ({ uploadDocument }));

import { document } from "../test/fixtures";
import { useUpload } from "./useUpload";

function pdf(name = "sheet.pdf", size = 1000): File {
  const file = new File(["x"], name);
  Object.defineProperty(file, "size", { value: size });
  return file;
}

beforeEach(() => {
  uploadDocument.mockReset();
});

describe("useUpload", () => {
  it("hands a processed document to the caller", async () => {
    uploadDocument.mockResolvedValue(document());
    const onComplete = vi.fn();

    const { result } = renderHook(() => useUpload({ onComplete }));
    act(() => result.current.start(pdf()));

    await waitFor(() => expect(onComplete).toHaveBeenCalled());
    expect(onComplete.mock.calls[0]?.[0]._id).toBe("doc-1");
  });

  it("treats a 201 rejection as a result, not a failure", async () => {
    const rejected = document({
      status: "rejected",
      rejection: {
        reason: "equation_unbalanced",
        message: "Assets do not equal liabilities plus equity.",
        at: "2026-08-28T00:00:00Z",
      },
    });
    uploadDocument.mockResolvedValue(rejected);
    const onComplete = vi.fn();

    const { result } = renderHook(() => useUpload({ onComplete }));
    act(() => result.current.start(pdf()));

    await waitFor(() => expect(onComplete).toHaveBeenCalled());
    expect(onComplete.mock.calls[0]?.[0].status).toBe("rejected");
    expect(result.current.state.kind).not.toBe("failed");
  });

  it("keeps a refused upload on the page instead of navigating", async () => {
    uploadDocument.mockRejectedValue(
      new ApiError("Not a Balance Sheet.", 422, "not_a_balance_sheet"),
    );
    const onComplete = vi.fn();

    const { result } = renderHook(() => useUpload({ onComplete }));
    act(() => result.current.start(pdf()));

    await waitFor(() => expect(result.current.state.kind).toBe("failed"));
    expect(onComplete).not.toHaveBeenCalled();
  });

  it("refuses an out-of-scope file without contacting the server", () => {
    const { result } = renderHook(() => useUpload({ onComplete: vi.fn() }));
    act(() => result.current.start(pdf("sheet.xls")));

    expect(uploadDocument).not.toHaveBeenCalled();
    expect(result.current.state).toMatchObject({
      kind: "rejected",
      rejection: { reason: "legacy_excel" },
    });
  });

  it("reports the file being processed while it waits", async () => {
    uploadDocument.mockReturnValue(new Promise(() => undefined));

    const { result } = renderHook(() => useUpload({ onComplete: vi.fn() }));
    act(() => result.current.start(pdf("meridian.pdf")));

    expect(result.current.state).toMatchObject({
      kind: "uploading",
      filename: "meridian.pdf",
      stageIndex: 0,
    });
  });

  it("returns to idle when the user stops waiting", async () => {
    uploadDocument.mockReturnValue(new Promise(() => undefined));

    const { result } = renderHook(() => useUpload({ onComplete: vi.fn() }));
    act(() => result.current.start(pdf()));
    act(() => result.current.cancel());

    expect(result.current.state.kind).toBe("idle");
  });
});
