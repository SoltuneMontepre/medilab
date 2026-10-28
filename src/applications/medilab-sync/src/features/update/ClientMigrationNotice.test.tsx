import { expect, test } from "bun:test";
import { renderToString } from "react-dom/server";
import { LocaleProvider } from "../../locale";
import { ClientMigrationNotice } from "./ClientMigrationNotice";

test("migration refusal is visible with a manual download action and preservation guidance", () => {
  const html = renderToString(<LocaleProvider locale="en"><ClientMigrationNotice notice={{
    message: "Install the current release <script>alert(1)</script>",
    download_url: "https://lims.example/download/sync.deb",
  }} /></LocaleProvider>);
  expect(html).toContain('role="alert"');
  expect(html).toContain("https://lims.example/download/sync.deb");
  expect(html).toContain("Open download page");
  expect(html).toContain("local files and queued work");
  expect(html).not.toContain("<script>");
});

test("a refusal without a safe URL asks for assistance without offering a download action", () => {
  const html = renderToString(<LocaleProvider locale="en"><ClientMigrationNotice notice={{message: "Update required", download_url: null}} /></LocaleProvider>);
  expect(html).toContain("administrator");
  expect(html).not.toContain("<button");
});
