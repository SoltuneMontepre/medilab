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
      if (method === "create") {
        this.put(args[0].key, args[0].value);
        return rows.get(args[0].key).id;
      }
      if (method === "write") {
        if (ignoreWrite) {
          ignoreWrite = false;
        } else {
          for (const row of rows.values()) if (args[0].includes(row.id)) this.put(row.key, args[1].value);
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

function deferred() {
  let resolve;
  const promise = new Promise((yes) => {
    resolve = yes;
  });
  return { promise, resolve };
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
    ["blank", false],
    ["empty", ""],
  ];
  const server = parameterServer(original);
  const tasks = tasksFor(server);
  const checkpoint = await tasks.odooCheckpointSettings({ login: "demo.administrator" });
  server.put("changed", "different");
  server.remove("deleted");
  server.put("blank", "changed");
  server.remove("empty");
  server.put("new.default", "not previously stored");
  assert.equal(await tasks.odooRestoreSettings({ checkpoint }), null);
  assert.deepEqual(
    server.snapshot(),
    [...original].sort(([a], [b]) => a.localeCompare(b)),
  );
  await assert.rejects(() => tasks.odooRestoreSettings({ checkpoint }), { message: "The settings checkpoint is unavailable." });
});

test("settings mutations finish one at a time before removing additions and verifying the snapshot", { timeout: 5000 }, async () => {
  const original = [
    ["first", "original first"],
    ["missing", "original missing"],
    ["last", "original last"],
  ];
  const server = parameterServer(original);
  const started = deferred();
  const release = deferred();
  const mutations = [];
  const tasks = settingsTasks(async (payload) => {
    if (["create", "write", "unlink"].includes(payload.method)) {
      mutations.push(payload.method);
      if (mutations.length === 1) {
        started.resolve();
        await release.promise;
      }
    }
    return server.call(payload);
  });
  const checkpoint = await tasks.odooCheckpointSettings({ login: "demo.administrator" });
  server.put("first", "changed first");
  server.remove("missing");
  server.put("last", "changed last");
  server.put("new.default", "added");
  const restoring = tasks.odooRestoreSettings({ checkpoint });
  try {
    await started.promise;
    assert.deepEqual(mutations, ["write"], "no later mutation starts while the first write is pending");
    assert.ok(server.snapshot().some(([key]) => key === "new.default"));
  } finally {
    release.resolve();
    await restoring;
  }
  assert.deepEqual(mutations, ["write", "create", "write", "unlink"]);
  assert.deepEqual(server.snapshot(), [...original].sort(([a], [b]) => a.localeCompare(b)));
});

test("a failed setting write stops later mutations and preserves its checkpoint for a complete retry", async () => {
  const original = [
    ["first", "original first"],
    ["second", "original second"],
    ["third", "original third"],
  ];
  const server = parameterServer(original);
  const mutations = [];
  const tasks = settingsTasks((payload) => {
    if (["create", "write", "unlink"].includes(payload.method)) mutations.push(structuredClone(payload));
    return server.call(payload);
  });
  const checkpoint = await tasks.odooCheckpointSettings({ login: "demo.administrator" });
  for (const [key] of original) server.put(key, "changed");
  server.put("new.default", "added");
  server.fail("write", new Error("Controlled second-write failure"), 2);

  await assert.rejects(() => tasks.odooRestoreSettings({ checkpoint }), { message: "The settings checkpoint could not be restored." });

  assert.deepEqual(mutations.map(({ args }) => args[0]), [[1], [2]]);
  assert.deepEqual(server.snapshot(), [
    ["first", "original first"],
    ["new.default", "added"],
    ["second", "changed"],
    ["third", "changed"],
  ]);
  assert.equal(await tasks.odooRestoreSettings({ checkpoint }), null);
  assert.deepEqual(server.snapshot(), [...original].sort(([a], [b]) => a.localeCompare(b)));
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
    ["write", 1],
    ["create", 1],
    ["unlink", 1],
    ["search_read", 2],
  ]) {
    const original = [["private.token", secret]];
    const server = parameterServer(original);
    const tasks = tasksFor(server);
    const checkpoint = await tasks.odooCheckpointSettings({ login: "demo.administrator" });
    server.put("private.token", "changed");
    if (method === "create") server.remove("private.token");
    server.put("new.default", secret);
    server.fail(method, backendError(), occurrence);
    await assertSafeRejection(() => tasks.odooRestoreSettings({ checkpoint }), "The settings checkpoint could not be restored.");
    assert.equal(await tasks.odooRestoreSettings({ checkpoint }), null);
    assert.deepEqual(
      server.snapshot(),
      [...original].sort(([a], [b]) => a.localeCompare(b)),
    );
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
