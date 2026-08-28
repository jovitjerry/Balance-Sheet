/**
 * A conversation belongs to exactly one document.
 *
 * The backend already keeps history out of `Context.groundable`, so a figure
 * repeated in an earlier turn cannot launder itself into evidence. That
 * protection is worth nothing if the client carries a thread from one document
 * onto another, so the thread is keyed by id and reset when the id changes.
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const askQuestion = vi.hoisted(() => vi.fn());
vi.mock("../api/insights", async () => {
  const actual = await vi.importActual<typeof import("../api/insights")>(
    "../api/insights",
  );
  return { ...actual, askQuestion };
});

import { answer } from "../test/fixtures";
import { useConversation } from "./useConversation";

beforeEach(() => {
  askQuestion.mockReset();
  askQuestion.mockResolvedValue(answer());
});

describe("useConversation", () => {
  it("records the question and its answer", async () => {
    const { result } = renderHook(() => useConversation("A"));

    act(() => result.current.ask("What is the current ratio?"));
    await waitFor(() => expect(result.current.exchanges).toHaveLength(1));

    expect(result.current.exchanges[0]?.question).toBe(
      "What is the current ratio?",
    );
  });

  it("clears the thread when the document changes", async () => {
    const { result, rerender } = renderHook(({ id }) => useConversation(id), {
      initialProps: { id: "A" },
    });

    act(() => result.current.ask("A question about document A"));
    await waitFor(() => expect(result.current.exchanges).toHaveLength(1));

    rerender({ id: "B" });

    expect(result.current.exchanges).toHaveLength(0);
  });

  it("does not merge threads when returning to an earlier document", async () => {
    const { result, rerender } = renderHook(({ id }) => useConversation(id), {
      initialProps: { id: "A" },
    });

    act(() => result.current.ask("about A"));
    await waitFor(() => expect(result.current.exchanges).toHaveLength(1));

    rerender({ id: "B" });
    rerender({ id: "A" });

    expect(result.current.exchanges).toHaveLength(0);
  });

  it("sends the question to the document currently being viewed", async () => {
    const { result } = renderHook(() => useConversation("doc-42"));

    act(() => result.current.ask("anything"));
    await waitFor(() => expect(askQuestion).toHaveBeenCalled());

    expect(askQuestion.mock.calls[0]?.[0]).toBe("doc-42");
  });

  it("sends prior turns as history, so follow-ups can be resolved", async () => {
    const { result } = renderHook(() => useConversation("A"));

    act(() => result.current.ask("What is the current ratio?"));
    await waitFor(() => expect(result.current.exchanges).toHaveLength(1));

    act(() => result.current.ask("Is that good?"));
    await waitFor(() => expect(result.current.exchanges).toHaveLength(2));

    const history = askQuestion.mock.calls[1]?.[2];
    expect(history).toHaveLength(1);
    expect(history[0].question).toBe("What is the current ratio?");
  });

  it("does not send a refusal as history - it carries nothing to build on", async () => {
    askQuestion.mockResolvedValueOnce(
      answer({ status: "refused", answer: null, reason: "out_of_scope" }),
    );

    const { result } = renderHook(() => useConversation("A"));

    act(() => result.current.ask("What was the net profit?"));
    await waitFor(() => expect(result.current.exchanges).toHaveLength(1));

    act(() => result.current.ask("How much inventory is there?"));
    await waitFor(() => expect(result.current.exchanges).toHaveLength(2));

    expect(askQuestion.mock.calls[1]?.[2]).toHaveLength(0);
  });

  it("ignores an empty question", () => {
    const { result } = renderHook(() => useConversation("A"));
    act(() => result.current.ask("   "));
    expect(askQuestion).not.toHaveBeenCalled();
  });

  it("surfaces a transport failure without losing the thread", async () => {
    const { result } = renderHook(() => useConversation("A"));

    act(() => result.current.ask("first"));
    await waitFor(() => expect(result.current.exchanges).toHaveLength(1));

    askQuestion.mockRejectedValueOnce(new Error("boom"));
    act(() => result.current.ask("second"));

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.exchanges).toHaveLength(1);
    expect(result.current.pending).toBeNull();
  });
});
