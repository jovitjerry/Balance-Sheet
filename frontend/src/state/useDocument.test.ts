/**
 * Document isolation, as an executable assertion.
 *
 * "Avoid mixing data between documents" is not something inspection can
 * establish. The failure it guards against is a race: a request for document A
 * that resolves *after* the user has moved to document B, overwriting B's
 * figures with A's under B's heading. Aborting on change does not close it -
 * an abort signal cannot un-resolve a promise that already settled.
 *
 * So the hook stamps every response with the id it was made for and discards
 * any that no longer matches. These tests hold it to that.
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { BalanceSheetDocument } from "../types/balanceSheet";

const getDocument = vi.hoisted(() => vi.fn());
vi.mock("../api/documents", () => ({ getDocument }));

import { useDocument } from "./useDocument";

function documentWithId(id: string): BalanceSheetDocument {
  return {
    _id: id,
    status: "analyzed",
    source: {
      filename: `${id}.pdf`,
      content_type: "application/pdf",
      size_bytes: 1,
      sha256: "0".repeat(64),
      ref: { backend: "local", key: id, size_bytes: 1, content_type: "application/pdf" },
    },
    errors: [],
    created_at: "2026-08-28T00:00:00Z",
    updated_at: "2026-08-28T00:00:00Z",
  };
}

/** A promise plus the handles to settle it whenever the test chooses. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

beforeEach(() => {
  getDocument.mockReset();
});

describe("useDocument", () => {
  it("loads the document named by its id", async () => {
    getDocument.mockResolvedValue(documentWithId("A"));

    const { result } = renderHook(() => useDocument("A"));

    await waitFor(() => expect(result.current.state.kind).toBe("ready"));
    expect(result.current.state).toMatchObject({
      kind: "ready",
      document: { _id: "A" },
    });
  });

  it("clears to loading the moment the id changes", async () => {
    getDocument.mockResolvedValue(documentWithId("A"));

    const { result, rerender } = renderHook(({ id }) => useDocument(id), {
      initialProps: { id: "A" },
    });
    await waitFor(() => expect(result.current.state.kind).toBe("ready"));

    // Never resolves, so the only thing that can clear A is the id change.
    getDocument.mockReturnValue(deferred<BalanceSheetDocument>().promise);
    rerender({ id: "B" });

    expect(result.current.state.kind).toBe("loading");
  });

  it("discards a response that arrives after the document has changed", async () => {
    const slowA = deferred<BalanceSheetDocument>();
    const fastB = documentWithId("B");

    getDocument.mockImplementation((id: string) =>
      id === "A" ? slowA.promise : Promise.resolve(fastB),
    );

    const { result, rerender } = renderHook(({ id }) => useDocument(id), {
      initialProps: { id: "A" },
    });

    rerender({ id: "B" });
    await waitFor(() => expect(result.current.state.kind).toBe("ready"));
    expect(result.current.state).toMatchObject({ document: { _id: "B" } });

    // A finally answers - long after the user moved on.
    await act(async () => {
      slowA.resolve(documentWithId("A"));
      await slowA.promise;
    });

    expect(result.current.state).toMatchObject({
      kind: "ready",
      document: { _id: "B" },
    });
  });

  it("discards a late failure from a document no longer being viewed", async () => {
    const slowA = deferred<BalanceSheetDocument>();

    getDocument.mockImplementation((id: string) =>
      id === "A" ? slowA.promise : Promise.resolve(documentWithId("B")),
    );

    const { result, rerender } = renderHook(({ id }) => useDocument(id), {
      initialProps: { id: "A" },
    });
    rerender({ id: "B" });
    await waitFor(() => expect(result.current.state.kind).toBe("ready"));

    await act(async () => {
      slowA.reject(new Error("A failed"));
      await slowA.promise.catch(() => undefined);
    });

    // B is still on screen; A's failure is not B's problem.
    expect(result.current.state).toMatchObject({
      kind: "ready",
      document: { _id: "B" },
    });
  });

  it("reports an error for the document actually being viewed", async () => {
    getDocument.mockRejectedValue(new Error("no such document"));

    const { result } = renderHook(() => useDocument("A"));

    await waitFor(() => expect(result.current.state.kind).toBe("error"));
  });

  it("requests nothing when there is no id", () => {
    renderHook(() => useDocument(undefined));
    expect(getDocument).not.toHaveBeenCalled();
  });
});
