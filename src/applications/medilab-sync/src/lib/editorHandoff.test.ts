import { expect, test } from "bun:test";
import { openEditorInBrowser } from "./editorHandoff";

test("browser handoff sends only a positive file ID to the native command", async () => {
  const calls: unknown[] = [];
  await openEditorInBrowser(42, async (command, args) => { calls.push({ command, args }); });
  expect(calls).toEqual([{ command: "open_office_editor", args: { fileId: 42 } }]);
});

test("invalid file IDs never invoke a browser command", async () => {
  for (const id of [0, -1, NaN, Infinity, 1.5, Number.MAX_SAFE_INTEGER + 1]) {
    await expect(openEditorInBrowser(id, async () => { throw new Error("must not invoke"); })).rejects.toThrow("Invalid laboratory file ID");
  }
});

test("launch errors reach the caller and a later attempt can succeed", async () => {
  await expect(openEditorInBrowser(1, async () => { throw new Error("launch failed"); })).rejects.toThrow("launch failed");
  await openEditorInBrowser(1, async () => {});
});
