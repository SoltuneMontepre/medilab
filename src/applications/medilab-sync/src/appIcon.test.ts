import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const app = join(import.meta.dir, "..");
const svg = (path: string) => readFileSync(path, "utf8").replace(/\r\n/g, "\n");
const webMark = svg(join(app, "../../core/modules/sol_theme/static/src/img/medilab.svg"));

test("the window and icon logos are the web's MediLab mark", () => {
  for (const logo of ["public/app-icon.svg", "src-tauri/icons/logo.svg"]) {
    expect(svg(join(app, logo))).toBe(webMark);
  }
});
