export function humanizeIdentifier(identifier: string): string {
  const words = identifier.replace(/_/g, " ").trim();
  if (!words) return identifier;
  return words.charAt(0).toUpperCase() + words.slice(1);
}
export function isIdentifier(value: string): boolean {
  return /^[a-z0-9]+(?:_[a-z0-9]+)*$/.test(value.trim());
}
export function sameConcept(a: string | null | undefined, b: string | null | undefined): boolean {
  if (!a || !b) return false;
  return reduce(a) === reduce(b);
}
function reduce(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "");
}
