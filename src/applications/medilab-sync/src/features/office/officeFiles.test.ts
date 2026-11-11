import { expect, test } from "bun:test";
import { canEditOnline, isOfficeDocument } from "./officeFiles";

test("only supported Office working and result files offer editing", () => {
  for (const path of ["a.docx", "nested/a.XLSX", "a.pptx"]) {
    expect(isOfficeDocument(path)).toBe(true);
    for (const category of ["working", "result", null, undefined]) expect(canEditOnline(path, category)).toBe(true);
    for (const category of ["raw", "report", "unknown"]) expect(canEditOnline(path, category)).toBe(false);
  }
  for (const path of ["a.pdf", "a.doc", "a.docx.exe", "a.csv", "a.odt"]) {
    expect(canEditOnline(path, "result")).toBe(false);
  }
});
