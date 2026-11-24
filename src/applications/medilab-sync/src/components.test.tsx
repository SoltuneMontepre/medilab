import { expect, test } from "bun:test";
import { renderToString } from "react-dom/server";
import { ConfirmDialog } from "./components";
import { LocaleProvider } from "./locale";

test("ConfirmDialog asks the question and names the action on its button", () => {
  const html = renderToString(
    <LocaleProvider locale="en">
      <ConfirmDialog
        title="Stop syncing HPLC?"
        body="Your files stay on this computer."
        confirmLabel="Stop syncing"
        onConfirm={() => {}}
        onCancel={() => {}}
      />
    </LocaleProvider>,
  );
  expect(html).toContain("<dialog");
  expect(html).toContain("Stop syncing HPLC?");
  expect(html).toContain("Your files stay on this computer.");
  expect(html).toContain(">Stop syncing</button>");
  expect(html).toContain(">Cancel</button>");
});
