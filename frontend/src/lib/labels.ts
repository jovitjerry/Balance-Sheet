/**
 * Turning the backend's identifiers into words, and telling near-duplicates
 * apart.
 *
 * Canonical labels and ratio names travel as snake_case identifiers
 * (`cash_and_cash_equivalents`, `debt_to_equity`) because that is what the
 * taxonomy and the formula set are keyed by. They are keys, not prose, and
 * showing them raw leaks the shape of the data model into the page.
 */

/** `long_term_borrowings` -> `Long term borrowings`. */
export function humanizeIdentifier(identifier: string): string {
  const words = identifier.replace(/_/g, " ").trim();
  if (!words) return identifier;
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Whether a string is a bare identifier rather than something already prose. */
export function isIdentifier(value: string): boolean {
  return /^[a-z0-9]+(?:_[a-z0-9]+)*$/.test(value.trim());
}

/**
 * Whether two labels name the same thing to a reader.
 *
 * "Cash and cash equivalents" and `cash_and_cash_equivalents` differ as
 * strings but say the same words, so printing the second beneath the first is
 * noise rather than information. Compared on letters and digits alone, which
 * ignores case, underscores, punctuation and spacing.
 */
export function sameConcept(a: string | null | undefined, b: string | null | undefined): boolean {
  if (!a || !b) return false;
  return reduce(a) === reduce(b);
}

function reduce(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "");
}
