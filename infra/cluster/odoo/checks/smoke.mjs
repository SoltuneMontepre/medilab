// Checks the colour behind ODOO_URL before Argo Rollouts switches traffic to it: the login page renders, /odoo sends
// visitors to it, and every asset bundle of the login page and the web client builds, parses and has no CSS error.
// A bundle that fails to build leaves people on a blank page while /web/health still passes.
import vm from "node:vm";

const base = process.env.ODOO_URL.replace(/\/$/, "");
const CSS_ERROR = "## CSS error message ##";
// A version no bundle has makes Odoo build the web client's bundles with this colour's code and redirect to them;
// "any" would serve whatever bundle is stored, such as the other colour's.
const WEB_CLIENT = ["/web/assets/0000000/web.assets_web.min.js", "/web/assets/0000000/web.assets_web.min.css"];
const failures = [];

async function fetchText(path, options = {}) {
  const response = await fetch(base + path, { signal: AbortSignal.timeout(120_000), ...options });
  return { response, text: options.redirect === "manual" ? "" : await response.text() };
}

async function checkBundle(path) {
  const { response, text } = await fetchText(path);
  if (response.status !== 200 || !text) {
    failures.push(`${path} answered ${response.status} with ${text.length} bytes`);
  } else if (path.includes(".css") && text.includes(CSS_ERROR)) {
    failures.push(`${path} has a CSS error: ${text.slice(text.indexOf(CSS_ERROR), text.indexOf(CSS_ERROR) + 300)}`);
  } else if (path.includes(".js")) {
    try {
      new vm.Script(text, { filename: path });
    } catch (error) {
      failures.push(`${path} does not parse: ${error.message}`);
    }
  }
  console.log(`${path}: ${response.status}, ${text.length} bytes${response.redirected ? ` from ${new URL(response.url).pathname}` : ""}`);
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
for (const path of new Set([...linked, ...WEB_CLIENT])) {
  await checkBundle(path);
}

if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log("The release serves its login page and builds its assets.");
