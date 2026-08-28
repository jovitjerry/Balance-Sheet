/**
 * Vitest setup, run once before every test file.
 *
 * `jest-dom` adds the DOM matchers (`toBeInTheDocument`, `toBeDisabled`); the
 * cleanup below unmounts anything a test rendered, so one test's markup can
 * never be found by the next one's query.
 */

import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});
