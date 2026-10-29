const assert = require("node:assert/strict");
const { webcrypto } = require("node:crypto");
const { readFile } = require("node:fs/promises");
const path = require("node:path");
const test = require("node:test");

let moduleId = 0;

async function support(t, crypto) {
  for (const [name, value] of Object.entries({ crypto, Cypress: undefined, cy: undefined, before: undefined, after: undefined })) {
    const original = Object.getOwnPropertyDescriptor(globalThis, name);
    Object.defineProperty(globalThis, name, { configurable: true, writable: true, value });
    t.after(() => {
      if (original) Object.defineProperty(globalThis, name, original);
      else delete globalThis[name];
    });
  }
  const source = await readFile(path.join(__dirname, "odoo.js"), "utf8");
  const url = `data:text/javascript;base64,${Buffer.from(source).toString("base64")}#${moduleId++}`;
  return { ...(await import(url)), url };
}

test("secure origins retain the native UUID generator", async (t) => {
  const id = "00000000-0000-4000-8000-000000000001";
  let calls = 0;
  const { randomId } = await support(t, {
    randomUUID() {
      calls += 1;
      return id;
    },
    getRandomValues() {
      assert.fail("native UUID generation must not use the fallback");
    },
  });
  assert.equal(randomId(), id);
  assert.equal(calls, 1);
});

test("HTTP origins without randomUUID preserve all sixteen random bytes, including leading zeroes", async (t) => {
  let calls = 0;
  const { randomId } = await support(t, {
    getRandomValues(bytes) {
      assert.ok(bytes instanceof Uint8Array);
      assert.equal(bytes.length, 16);
      calls += 1;
      bytes.set(Array.from({ length: 16 }, (_, index) => index));
      return bytes;
    },
  });
  assert.equal(randomId(), "000102030405060708090a0b0c0d0e0f");
  assert.equal(calls, 1);
});

test("WF-03 loads, owns its hooks and scopes distinct calls when only getRandomValues is available", async (t) => {
  let randomCalls = 0;
  const helpers = await support(t, {
    getRandomValues(bytes) {
      randomCalls += 1;
      return webcrypto.getRandomValues(bytes);
    },
  });
  const exposed = new Map();
  const calls = [];
  const hooks = {};
  const spec = "cypress/e2e/flows/wf-03-testing-scheduling/testing-scheduling.cy.js";
  globalThis.Cypress = {
    spec: { relative: spec },
    currentTest: { titlePath: ["WF-03", "schedules a test"] },
    expose(name, value) {
      if (arguments.length > 1) exposed.set(name, value);
      return exposed.get(name);
    },
  };
  globalThis.cy = {
    task(name, payload, options) {
      calls.push({ name, payload: structuredClone(payload), options });
      return Promise.resolve(null);
    },
  };
  globalThis.before = (hook) => (hooks.before = hook);
  globalThis.after = (hook) => (hooks.after = hook);
  const source = (await readFile(path.join(__dirname, "wf03.js"), "utf8")).replace('from "./odoo"', `from "${helpers.url}"`);
  await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}#${moduleId++}`);
  assert.equal(typeof hooks.before, "function", "support-file loading must reach hook registration");
  await hooks.before();
  const execution = exposed.get("wf03Execution");
  assert.match(execution.id, /^[0-9a-f]{32}$/);
  assert.equal(execution.spec, spec);
  await helpers.callAs("demo.tester", "medilab.machine.booking", "search", [[]]);
  await helpers.task("odooCheckpointSettings", { login: "demo.administrator" }, { log: false });
  const ids = new Set([execution.id]);
  for (const { payload } of calls.slice(1)) {
    assert.equal(payload.execution.id, execution.id);
    assert.equal(payload.execution.spec, spec);
    assert.equal(payload.execution.test, "WF-03 > schedules a test");
    assert.match(payload.execution.callId, /^[0-9a-f]{32}$/);
    ids.add(payload.execution.callId);
  }
  assert.equal(ids.size, 3);
  assert.equal(randomCalls, 3);
  await hooks.after();
  assert.deepEqual(calls.map(({ name }) => name), ["odooBeginExecution", "odooCall", "odooCheckpointSettings", "odooEndExecution"]);
  assert.deepEqual(calls[0].payload, execution);
  assert.deepEqual(calls[3].payload, execution);
  assert.equal(exposed.get("wf03Execution"), null);
});
