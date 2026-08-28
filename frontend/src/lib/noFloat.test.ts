/**
 * A structural check, not a behavioural one.
 *
 * The backend refuses to let a monetary value become a `float` - `to_decimal`
 * in `core/money.py` raises on one rather than accept the drift. That
 * guarantee survives the network only if nothing on this side coerces a figure
 * back into an IEEE double, and no amount of care in review keeps that true
 * across future edits.
 *
 * So it is enforced the way `tests/test_pipeline.py::TestModuleBoundaries`
 * enforces the backend's module boundaries: by reading the source and failing
 * on the thing that must not appear.
 *
 * Test files are excluded - they are not shipped, and this file necessarily
 * contains every string it bans.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

// Resolved from the working directory rather than `import.meta.url`: under the
// jsdom environment that URL is not a `file:` one, and `fileURLToPath` throws.
// Vitest runs with the project root as cwd.
const SRC = join(process.cwd(), "src");

/**
 * Each of these turns a decimal string into a binary float. `toFixed` is here
 * because it is the tempting shortcut for rounding a ratio, and it rounds a
 * value that has already lost precision by the time it is called.
 */
const FORBIDDEN: ReadonlyArray<{ pattern: RegExp; why: string }> = [
  { pattern: /\bparseFloat\s*\(/, why: "parseFloat produces a binary float" },
  { pattern: /\bparseInt\s*\(/, why: "parseInt truncates and cannot hold a Decimal" },
  { pattern: /\bNumber\s*\(/, why: "Number() produces a binary float" },
  { pattern: /\.toFixed\s*\(/, why: "toFixed rounds a value that is already a float" },
  {
    pattern: /\bvalueAsNumber\b/,
    why: "valueAsNumber reads an input as a binary float",
  },
];

/**
 * Blank out comments, preserving line numbering.
 *
 * Prose explaining *why* a coercion is forbidden necessarily names it, and a
 * guard that fires on its own rationale is one somebody switches off. String
 * literals are deliberately left intact, so a banned call hidden in one is
 * still caught.
 */
function stripComments(source: string): string {
  const blank = (match: string) => match.replace(/[^\n]/g, " ");
  return source
    .replace(/\/\*[\s\S]*?\*\//g, blank)
    .replace(/\/\/[^\n]*/g, blank);
}

function sourceFiles(dir: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      found.push(...sourceFiles(full));
      continue;
    }
    if (!/\.tsx?$/.test(entry)) continue;
    if (/\.test\.tsx?$/.test(entry)) continue;
    found.push(full);
  }
  return found;
}

describe("no figure is ever coerced to a JavaScript number", () => {
  const files = sourceFiles(SRC);

  it("finds source files to check", () => {
    // Guards the guard: a broken walker would make every assertion below pass
    // vacuously, which is the classic way a structural check dies quietly.
    expect(files.length).toBeGreaterThan(0);
  });

  it.each(FORBIDDEN)("does not use $pattern - $why", ({ pattern }) => {
    const offenders: string[] = [];

    for (const file of files) {
      const source = stripComments(readFileSync(file, "utf8"));
      source.split("\n").forEach((line, index) => {
        if (pattern.test(line)) {
          offenders.push(`${relative(SRC, file)}:${index + 1}: ${line.trim()}`);
        }
      });
    }

    expect(offenders).toEqual([]);
  });
});
