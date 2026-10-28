const assert = require("node:assert/strict");
const test = require("node:test");
const { settingsTasks } = require("./settings");

function parameterServer(initial) {
  const rows = new Map(initial.map(([key, value], index) => [key, { id: index + 1, key, value }]));
  let nextId = rows.size;
  let failure;
  let ignoreWrite = false;

  return {
    snapshot: () => [...rows.values()].map(({ key, value }) => [key, value]).sort(([a], [b]) => a.localeCompare(b)),
    put(key, value) {
      rows.set(key, { id: rows.get(key)?.id ?? ++nextId, key, value });
    },
    remove: (key) => rows.delete(key),
    fail(method, error, occurrence = 1) {
      failure = { method, error, remaining: occurrence };
    },
    ignoreNextWrite() {
      ignoreWrite = true;
    },
    async call({ model, method, args }) {
      assert.equal(model, "ir.config_parameter");
      if (failure?.method === method && --failure.remaining === 0) {
        const error = failure.error;
        failure = undefined;
        throw error;
      }
      if (method === "search_read") return [...rows.values()].map((row) => ({ ...row }));
      if (method === "set_param") {
        if (ignoreWrite) {
          ignoreWrite = false;
        } else {
          this.put(args[0], args[1]);
        }
        return null;
      }
      if (method === "unlink") {
        for (const [key, row] of rows) if (args[0].includes(row.id)) rows.delete(key);
        return true;
      }
      assert.fail("Unexpected parameter operation.");
    },
  };
}

function tasksFor(server) {
  return settingsTasks(server.call.bind(server));
}

test("a settings checkpoint exposes only an opaque reference", async () => {
  const secret = "FAKE-SECRET-ONLY-FOR-CONTRACT-TEST";
  const server = parameterServer([
    ["private.token", secret],
    ["ordinary.value", "original"],
  ]);
  const tasks = tasksFor(server);
  const checkpoint = await tasks.odooCheckpointSettings({ login: "demo.administrator" });
  assert.ok(typeof checkpoint === "number" || typeof checkpoint === "string");
  assert.equal(JSON.stringify(checkpoint).includes(secret), false);
  assert.deepEqual(Object.keys(tasks).sort(), ["odooCheckpointSettings", "odooRestoreSettings"]);
  assert.equal(await tasks.odooRestoreSettings({ checkpoint }), null);
});

test("restoration repairs changed and deleted settings and removes newly saved defaults", async () => {
  const original = [
    ["changed", "original"],
    ["deleted", "restore me"],
    ["untouched", "keep me"],
  ];
  const server = parameterServer(original);
  const tasks = tasksFor(server);
  const checkpoint = await tasks.odooCheckpointSettings({ login: "demo.administrator" });
  server.put("changed", "different");
  server.remove("deleted");
  server.put("new.default", "not previously stored");
  assert.equal(await tasks.odooRestoreSettings({ checkpoint }), null);
  assert.deepEqual(server.snapshot(), original);
  await assert.rejects(() => tasks.odooRestoreSettings({ checkpoint }), { message: "The settings checkpoint is unavailable." });
});

test("backend failures are redacted and a failed restoration retains its checkpoint for retry", async () => {
  const secret = "FAKE-BACKEND-SECRET-MUST-NOT-ESCAPE";
  function backendError() {
    const error = new Error(`Backend rejected ${secret}`);
    error.stack = `Original backend stack contains ${secret}`;
    error.cause = new Error(secret);
    return error;
  }
  async function assertSafeRejection(action, message) {
    await assert.rejects(action, (error) => {
      assert.equal(error.message, message);
      assert.equal(error.cause, undefined);
      assert.equal(error.stack.includes(secret), false);
      assert.equal(JSON.stringify(error).includes(secret), false);
      return true;
    });
  }

  const failedSnapshot = parameterServer([["private.token", secret]]);
  const snapshotTasks = tasksFor(failedSnapshot);
  failedSnapshot.fail("search_read", backendError());
  await assertSafeRejection(
    () => snapshotTasks.odooCheckpointSettings({ login: "demo.administrator" }),
    "The settings checkpoint could not be created.",
  );
  const recovered = await snapshotTasks.odooCheckpointSettings({ login: "demo.administrator" });
  assert.equal(await snapshotTasks.odooRestoreSettings({ checkpoint: recovered }), null);

  for (const [method, occurrence] of [
    ["search_read", 1],
    ["set_param", 1],
    ["unlink", 1],
    ["search_read", 2],
  ]) {
    const original = [["private.token", secret]];
    const server = parameterServer(original);
    const tasks = tasksFor(server);
    const checkpoint = await tasks.odooCheckpointSettings({ login: "demo.administrator" });
    server.put("private.token", "changed");
    server.put("new.default", secret);
    server.fail(method, backendError(), occurrence);
    await assertSafeRejection(() => tasks.odooRestoreSettings({ checkpoint }), "The settings checkpoint could not be restored.");
    assert.equal(await tasks.odooRestoreSettings({ checkpoint }), null);
    assert.deepEqual(server.snapshot(), original);
  }

  const server = parameterServer([["private.token", secret]]);
  const tasks = tasksFor(server);
  const checkpoint = await tasks.odooCheckpointSettings({ login: "demo.administrator" });
  server.put("private.token", "changed");
  server.ignoreNextWrite();
  await assertSafeRejection(() => tasks.odooRestoreSettings({ checkpoint }), "The settings checkpoint could not be restored.");
  assert.equal(await tasks.odooRestoreSettings({ checkpoint }), null);
  assert.deepEqual(server.snapshot(), [["private.token", secret]]);
});
