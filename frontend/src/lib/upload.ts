/**
 * Client-side upload checks.
 *
 * These mirror `core/config.py` defaults so an obviously-wrong file is
 * refused without a round trip. They are **not** a security control and are not
 * relied on as one: the backend validates by content rather than by extension
 * and enforces the size cap while streaming, because a filename and a reported
 * size are both attacker-controlled. This only saves the user a wasted minute.
 */

/** `max_upload_bytes` in `core/config.py`. */
export const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;

/** `allowed_extensions` in `core/config.py`. */
export const ALLOWED_EXTENSIONS = [".pdf", ".xlsx"] as const;

export const ACCEPT_ATTRIBUTE =
  ".pdf,.xlsx,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

export interface FileRejection {
  reason: "extension" | "legacy_excel" | "too_large" | "empty";
  message: string;
}

export function checkFile(file: File): FileRejection | null {
  const name = file.name.toLowerCase();

  if (name.endsWith(".xls")) {
    return {
      reason: "legacy_excel",
      message:
        "Legacy .xls files are out of scope - only .xlsx is supported. " +
        "Re-save the workbook as .xlsx and upload it again.",
    };
  }

  if (!ALLOWED_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return {
      reason: "extension",
      message: "Choose a PDF or an .xlsx workbook.",
    };
  }

  if (file.size === 0) {
    return { reason: "empty", message: "That file is empty." };
  }

  if (file.size > MAX_UPLOAD_BYTES) {
    return {
      reason: "too_large",
      message: `That file is ${formatBytes(file.size)}. The limit is ${formatBytes(
        MAX_UPLOAD_BYTES,
      )}.`,
    };
  }

  return null;
}

/**
 * A file size for display.
 *
 * Sizes are genuine JavaScript numbers - `File.size` is one, and no accounting
 * figure passes through here - so ordinary arithmetic is correct. It is kept
 * out of `money.ts` precisely so that file stays free of it.
 */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const rounded = Math.round(value * 10) / 10;
  return `${rounded} ${units[unit]}`;
}
