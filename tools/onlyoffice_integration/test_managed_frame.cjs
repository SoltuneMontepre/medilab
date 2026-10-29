const assert = require("node:assert/strict");
const { test } = require("node:test");
const { isDocumentEditorFrame } = require("./managed_frame.cjs");
const origin = "http://localhost:30000";
const suffix = "/web-apps/apps/documenteditor/main/index.html";
const version = "/9.4.0-28f4b6f6e0340fc826a03d403e4a14d1";
test("recognizes the observed versioned frame while retaining strict origin", () => {
  assert.equal(isDocumentEditorFrame(origin + version + suffix + "?opaque=not-logged", origin), true);
  assert.equal(isDocumentEditorFrame(origin + suffix, origin), true);
});
test("refuses foreign origins credentials modules and noncanonical prefixes", () => {
  for (const value of [
    "http://localhost:30001" + version + suffix, "https://localhost:30000" + version + suffix,
    "http://user:key@localhost:30000" + version + suffix, origin + "/foreign" + suffix,
    origin + version + suffix.replace("documenteditor", "spreadsheeteditor"), "not a URL",
  ]) assert.equal(isDocumentEditorFrame(value, origin), false);
});
