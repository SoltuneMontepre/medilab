// Runs the release smoke check against a stand-in Odoo for each way a colour can be sound or broken.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const SMOKE = fileURLToPath(new URL("../../../infra/cluster/odoo/checks/smoke.mjs", import.meta.url));
const LOGIN = `<form class="oe_login_form"></form>
<link href="/web/assets/1/web.assets_frontend.min.css"/><script src="/web/assets/1/web.assets_frontend.min.js"></script>`;

function sound() {
  return {
    "/web/login": [200, LOGIN],
    "/odoo": [303, "", { location: "/web/login?redirect=%2Fodoo" }],
    "/web/assets/1/web.assets_frontend.min.css": [200, "body{color:red}"],
    "/web/assets/1/web.assets_frontend.min.js": [200, "odoo.define('a', [], function () { return 1; });"],
    "/web/assets/0000000/web.assets_web.min.js": [302, "", { location: "/web/assets/abc/web.assets_web.min.js" }],
    "/web/assets/abc/web.assets_web.min.js": [200, "const web = 1;"],
    "/web/assets/0000000/web.assets_web.min.css": [200, ".o_web_client{}"],
  };
}

async function smoke(routes) {
  const server = createServer((request, response) => {
    const [status, body, headers] = routes[request.url] ?? [404, ""];
    response.writeHead(status, headers);
    response.end(body);
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const env = { ...process.env, ODOO_URL: `http://127.0.0.1:${server.address().port}/` };
  const child = spawn(process.execPath, [SMOKE], { env });
  let output = "";
  child.stdout.on("data", (chunk) => (output += chunk));
  child.stderr.on("data", (chunk) => (output += chunk));
  const code = await new Promise((resolve) => child.on("close", resolve));
  server.close();
  return { code, output };
}

test("a sound colour passes and names the bundle Odoo built", async () => {
  const { code, output } = await smoke(sound());

  assert.equal(code, 0, output);
  assert.match(output, /web\.assets_web\.min\.js: 200, 14 bytes from \/web\/assets\/abc\/web\.assets_web\.min\.js/);
  assert.match(output, /builds its assets/);
});

test("a stylesheet with Odoo's CSS error marker fails", async () => {
  const routes = sound();
  routes["/web/assets/0000000/web.assets_web.min.css"] = [200, "/* ## CSS error message ##: undefined variable */"];

  const { code, output } = await smoke(routes);

  assert.equal(code, 1);
  assert.match(output, /web\.assets_web\.min\.css has a CSS error: ## CSS error message ##: undefined variable/);
});

test("a script that does not parse fails", async () => {
  const routes = sound();
  routes["/web/assets/abc/web.assets_web.min.js"] = [200, "const = ;"];

  const { code, output } = await smoke(routes);

  assert.equal(code, 1);
  assert.match(output, /web\.assets_web\.min\.js does not parse: .*SyntaxError/s);
});

test("a missing login form, a bad redirect and a missing bundle each fail", async () => {
  const routes = sound();
  routes["/web/login"] = [200, '<p>Maintenance</p><script src="/web/assets/1/web.assets_frontend.min.js"></script>'];
  routes["/odoo"] = [200, "<p>Maintenance</p>"];
  delete routes["/web/assets/1/web.assets_frontend.min.js"];

  const { code, output } = await smoke(routes);

  assert.equal(code, 1);
  assert.match(output, /\/web\/login answered 200 without the login form/);
  assert.match(output, /\/odoo answered 200 to nowhere instead of the login page/);
  assert.match(output, /web\.assets_frontend\.min\.js answered 404 with 0 bytes/);
});
