// Checks the colour behind ODOO_URL before Argo Rollouts switches traffic to it: the login page renders, /odoo sends
// visitors to it, and every asset bundle of the login page and the web client builds, parses and has no CSS error.
// A bundle that fails to build leaves people on a blank page while /web/health still passes.
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const base = process.env.ODOO_URL.replace(/\/$/, "");
const CSS_ERROR = "## CSS error message ##";
// A version no bundle has makes Odoo build the web client's bundles with this colour's code and redirect to them;
// "any" would serve whatever bundle is stored, such as the other colour's.
const WEB_CLIENT = ["/web/assets/0000000/web.assets_web.min.js", "/web/assets/0000000/web.assets_web.min.css"];
const scratch = mkdtempSync(join(tmpdir(), "odoo-smoke-"));
const failures = [];
let parsed = 0;

async function fetchText(path, options = {}) {
  const response = await fetch(base + path, { signal: AbortSignal.timeout(120_000), ...options });
  return { response, text: options.redirect === "manual" ? "" : await response.text() };
}

// Node only parses the bundle, without running it.
function parseError(text) {
  parsed += 1;
  const file = join(scratch, `${parsed}.js`);
  writeFileSync(file, text);
  const result = spawnSync(process.execPath, ["--check", file], { encoding: "utf8" });
  return result.status === 0 ? "" : result.stderr.trim();
}

// Lines quote what the colour answered, so control characters are collapsed before they reach the log.
function oneLine(text) {
  return text.replace(/[\u0000-\u001f\u007f]+/g, " ");
}

async function checkBundle(path) {
  const { response, text } = await fetchText(path);
  if (response.status !== 200 || !text) {
    failures.push(`${path} answered ${response.status} with ${text.length} bytes`);
  } else if (path.includes(".css") && text.includes(CSS_ERROR)) {
    const start = text.indexOf(CSS_ERROR);
    failures.push(`${path} has a CSS error: ${text.slice(start, start + 300)}`);
  } else if (path.includes(".js")) {
    const error = parseError(text);
    if (error) {
      failures.push(`${path} does not parse: ${error}`);
    }
  }
  const served = response.redirected ? " from " + new URL(response.url).pathname : "";
  return `${path}: ${response.status}, ${text.length} bytes${served}`;
}

const login = await fetchText("/web/login");
if (login.response.status !== 200 || !login.text.includes("oe_login_form")) {
  failures.push(`/web/login answered ${login.response.status} without the login form`);
}
const odoo = await fetchText("/odoo", { redirect: "manual" });
const location = odoo.response.headers.get("location") ?? "";
if (![302, 303].includes(odoo.response.status) || !location.includes("/web/login")) {
  failures.push(`/odoo answered ${odoo.response.status} to ${location || "nowhere"} instead of the login page`);
}
const linked = [...login.text.matchAll(/(?:href|src)="(\/web\/assets\/[^"]+)"/g)].map((match) => match[1]);
const bundles = await Promise.all([...new Set([...linked, ...WEB_CLIENT])].map(checkBundle));
console.log(bundles.map(oneLine).join("\n"));
rmSync(scratch, { recursive: true, force: true });

if (failures.length) {
  console.error(failures.map(oneLine).join("\n"));
  process.exit(1);
}
console.log("The release serves its login page and builds its assets.");
