import { describe, expect, it } from "vitest";
import { checkFile, formatBytes, MAX_UPLOAD_BYTES } from "./upload";

function fileOf(name: string, size: number): File {
  const file = new File(["x"], name);
  // `File.size` is read-only, so it is redefined rather than constructed.
  Object.defineProperty(file, "size", { value: size });
  return file;
}

describe("checkFile", () => {
  it("accepts a PDF and an xlsx", () => {
    expect(checkFile(fileOf("sheet.pdf", 1000))).toBeNull();
    expect(checkFile(fileOf("sheet.xlsx", 1000))).toBeNull();
    expect(checkFile(fileOf("SHEET.PDF", 1000))).toBeNull();
  });

  it("refuses .xls as out of scope rather than as a malformed file", () => {
    const rejection = checkFile(fileOf("sheet.xls", 1000));
    expect(rejection?.reason).toBe("legacy_excel");
    expect(rejection?.message).toMatch(/out of scope/i);
  });

  it("refuses an unsupported extension", () => {
    expect(checkFile(fileOf("sheet.csv", 1000))?.reason).toBe("extension");
    expect(checkFile(fileOf("sheet.docx", 1000))?.reason).toBe("extension");
  });

  it("refuses an empty file", () => {
    expect(checkFile(fileOf("sheet.pdf", 0))?.reason).toBe("empty");
  });

  it("refuses a file over the cap and says how big it was", () => {
    const rejection = checkFile(fileOf("sheet.pdf", MAX_UPLOAD_BYTES + 1));
    expect(rejection?.reason).toBe("too_large");
    expect(rejection?.message).toMatch(/25 MB/);
  });

  it("accepts a file exactly at the cap", () => {
    expect(checkFile(fileOf("sheet.pdf", MAX_UPLOAD_BYTES))).toBeNull();
  });
});

describe("formatBytes", () => {
  it("scales to a readable unit", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatBytes(MAX_UPLOAD_BYTES)).toBe("25 MB");
  });
});
