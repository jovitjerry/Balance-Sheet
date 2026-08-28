import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import { describeError } from "./errors";

describe("describeError", () => {
  it("shows the backend's own message, which is safe to display verbatim", () => {
    const error = new ApiError("Not a Balance Sheet.", 422, "not_a_balance_sheet");
    expect(describeError(error).message).toBe("Not a Balance Sheet.");
  });

  it("says the API is not running rather than blaming the server", () => {
    // The dev proxy answers a refused connection with this code. Before it
    // existed the same situation surfaced as a bare 500 - "something went
    // wrong on the server" - which contradicted the header's own indicator.
    const error = new ApiError("The API is not running.", 502, "backend_unreachable");
    const described = describeError(error);

    expect(described.guidance).toMatch(/Nothing is listening on port 8000/);
    expect(described.guidance).not.toMatch(/went wrong on the server/);
    expect(described.retryable).toBe(true);
  });

  it("still has something useful to say for a 502 with no code", () => {
    expect(describeError(new ApiError("Bad gateway", 502)).guidance).toMatch(
      /could not be reached/i,
    );
  });

  it("keeps a genuine server fault described as one", () => {
    expect(describeError(new ApiError("Boom", 500)).guidance).toMatch(
      /went wrong on the server/,
    );
  });

  it("degrades safely on something that is not an ApiError", () => {
    expect(describeError("a string").message).toBe("Something went wrong.");
    expect(describeError(new Error("plain")).message).toBe("plain");
  });
});
