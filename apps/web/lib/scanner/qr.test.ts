import { describe, expect, it } from "vitest";
import { bibFromQr, normalizeBib } from "./qr";

const TOKEN = "R1.H0042.276d64b10f524f92a949d9c29d0d8002.ZNrzLT2Wxvbijz4SRkdA7w";

describe("bibFromQr", () => {
  it("reads the bib from an EkitiRun QR token", () => {
    expect(bibFromQr(TOKEN)).toBe("H0042");
    expect(bibFromQr(`  ${TOKEN}\n`)).toBe("H0042");
  });

  it("rejects anything else", () => {
    for (const raw of ["H0042", "https://example.com", "R1.H0042.short.sig", "", "R2." + TOKEN.slice(3)]) {
      expect(bibFromQr(raw)).toBeNull();
    }
  });
});

describe("normalizeBib", () => {
  it.each([
    ["H0042", "H0042"],
    ["h42", "H0042"],
    [" f 7 ", "F0007"],
    ["T0001", "T0001"],
  ])("%s -> %s", (typed, bib) => {
    expect(normalizeBib(typed)).toBe(bib);
  });

  it.each(["", "42", "HH42", "H12345", "H-42"])("rejects %j", (typed) => {
    expect(normalizeBib(typed)).toBeNull();
  });
});
