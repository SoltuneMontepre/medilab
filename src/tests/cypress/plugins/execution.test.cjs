const assert = require("node:assert/strict");
const { randomUUID } = require("node:crypto");
const { spawn } = require("node:child_process");
const { once } = require("node:events");
const { mkdtemp, rm } = require("node:fs/promises");
const { tmpdir } = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { executionTasks } = require("./execution");

const ADMINISTRATOR = "demo.administrator";
const SPEC = "cypress/e2e/flows/wf-03-testing-scheduling/testing-scheduling.cy.js";
const ORIGINAL_NEXTCALL = "2026-10-29 04:35:00";
const SECRET = "FAKE-PRIVATE-SETTING-MUST-NOT-ENTER-TRACE";

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

function scope() {
  return { id: randomUUID(), spec: SPEC };
}

function operation(execution, overrides = {}) {
  return {
    login: ADMINISTRATOR,
    model: "medilab.task",
    method: "create",
    args: [{ name: "Owned contract task" }],
    execution: { ...execution, test: "controlled lifecycle", callId: randomUUID() },
    ...overrides,
  };
}

function server({ active = true, databaseUuid = randomUUID() } = {}) {
  const cron = { id: 29, active, nextcall: ORIGINAL_NEXTCALL };
  const reminder = { id: 18, enabled: false };
  const fixtures = { taskActive: false, bookingActive: false };
  const calls = [];
  const controls = [];
  const settings = new Map([["private.token", SECRET]]);
  let nextCheckpoint = 0;
  const checkpoints = new Map();
  let restoreFailure;

  function intercept(predicate, action) {
    controls.push({ predicate, action });
  }

  async function call(payload) {
    const { model, method, args = [], kwargs = {} } = payload;
    calls.push(structuredClone(payload));
    const index = controls.findIndex(({ predicate }) => predicate(payload));
    if (index >= 0) return controls.splice(index, 1)[0].action(payload);
    if (model === "ir.config_parameter" && method === "get_str") {
      assert.deepEqual(args, ["database.uuid"]);
      return databaseUuid;
    }
    if (model === "ir.model.data" && method === "check_object_reference") {
      assert.equal(args[0], "sol_laboratory");
      if (args[1] === "ir_cron_notifications_remind") {
        return ["ir.cron", cron.active || kwargs.context?.active_test === false ? cron.id : false];
      }
      if (args[1] === "event_task_reminder") return ["mail.message.subtype", reminder.id];
    }
    if (model === "ir.cron" && method === "read") {
      assert.deepEqual(args[0], [cron.id]);
      return [{ ...cron }];
    }
    if (model === "ir.cron" && method === "write") {
      assert.deepEqual(args[0], [cron.id]);
      assert.ok(Object.keys(args[1]).every((field) => ["active", "nextcall"].includes(field)));
      Object.assign(cron, args[1]);
      return true;
    }
    if (model === "ir.cron" && method === "method_direct_trigger") {
      assert.deepEqual(args, [[cron.id]]);
      cron.nextcall = "2026-10-29 04:40:00";
      return true;
    }
    if (model === "mail.message.subtype" && method === "read") {
      assert.deepEqual(args[0], [reminder.id]);
      return [{ ...reminder }];
    }
    if (model === "mail.message.subtype" && method === "write") {
      assert.deepEqual(args[0], [reminder.id]);
      assert.deepEqual(Object.keys(args[1]), ["enabled"]);
      Object.assign(reminder, args[1]);
      return true;
    }
    if (model === "medilab.task" && method === "create") {
      fixtures.taskActive = true;
      return 100;
    }
    if (model === "medilab.test.request" && method === "create") return 200;
    if (model === "medilab.machine.booking" && ["search", "search_count"].includes(method)) {
      assert.deepEqual(args, [
        [
          ["sample_test_id.sample_id.request_id", "in", [200]],
          ["status", "in", ["queued", "scheduled"]],
        ],
      ]);
      return method === "search" ? (fixtures.bookingActive ? [300] : []) : Number(fixtures.bookingActive);
    }
    if (model === "medilab.machine.booking" && method === "action_cancel") {
      assert.deepEqual(args, [[300]]);
      fixtures.bookingActive = false;
      return true;
    }
    if (model === "medilab.task" && ["search", "search_count"].includes(method)) {
      assert.deepEqual(args, [
        [
          ["id", "in", [100]],
          ["document_model", "=", false],
          ["status", "not in", ["done", "cancelled"]],
        ],
      ]);
      return method === "search" ? (fixtures.taskActive ? [100] : []) : Number(fixtures.taskActive);
    }
    if (model === "medilab.task" && method === "action_cancel") {
      assert.deepEqual(args, [[100]]);
      fixtures.taskActive = false;
      return true;
    }
    assert.fail(`Unexpected ORM operation ${model}.${method} ${JSON.stringify({ args, kwargs })}`);
  }

  return {
    call,
    calls,
    cron,
    reminder,
    fixtures,
    intercept,
    settings,
    checkpoints,
    failRestore(error) {
      restoreFailure = error;
    },
    settingsTasks: {
      async odooCheckpointSettings({ login }) {
        assert.equal(login, ADMINISTRATOR);
        const id = ++nextCheckpoint;
        checkpoints.set(id, new Map(settings));
        return id;
      },
      async odooRestoreSettings({ checkpoint }) {
        if (restoreFailure) {
          const error = restoreFailure;
          restoreFailure = undefined;
          throw error;
        }
        assert.ok(checkpoints.has(checkpoint), "checkpoint retained until restoration succeeds");
        const saved = checkpoints.get(checkpoint);
        settings.clear();
        for (const [key, value] of saved) settings.set(key, value);
        checkpoints.delete(checkpoint);
        return null;
      },
    },
  };
}

async function harness(t, options = {}) {
  const lockDirectory = await mkdtemp(path.join(tmpdir(), "medilab-execution-contract-"));
  const backend = server(options);
  const instances = [];
  const trace = [];
  const create = (overrides = {}) => {
    const tasks = executionTasks({
      call: backend.call,
      settings: backend.settingsTasks,
      baseUrl: "http://127.0.0.1:32669",
      lockDirectory,
      trace: (event) => trace.push(event),
      deadlineMs: 100,
      ...overrides,
    });
    instances.push(tasks);
    return tasks;
  };
  t.after(async () => {
    for (const tasks of instances.reverse()) await tasks.cleanup();
    await rm(lockDirectory, { recursive: true, force: true });
  });
  return { ...backend, create, trace, lockDirectory };
}

test("a live owner excludes another execution on the same application before any mutation", async (t) => {
  const h = await harness(t);
  const owner = h.create();
  const contender = h.create();
  const first = scope();
  await owner.begin(first);
  const count = h.calls.length;
  await assert.rejects(() => contender.begin(scope()), /active|owned|running|lease|another/i);
  assert.ok(
    h.calls.slice(count).every(({ model, method }) => model === "ir.config_parameter" && method === "get_str"),
    "a rejected owner may identify the database but must not touch its state",
  );
  const independent = h.create({ call: server().call });
  const other = scope();
  await independent.begin(other);
  await independent.finish(other);
  await owner.finish(first);
});

test("invalid begin input leaves the current execution open without touching application state", async (t) => {
  const h = await harness(t);
  const tasks = h.create();
  const execution = scope();
  await tasks.begin(execution);
  for (const invalid of [
    { id: "", spec: SPEC },
    { id: randomUUID(), spec: "" },
    { id: 1, spec: SPEC },
  ]) {
    const count = h.calls.length;
    await assert.rejects(() => tasks.begin(invalid), /execution|scope|own/i);
    assert.equal(h.calls.length, count, "invalid input cannot restore or release the existing execution");
  }
  assert.equal(await tasks.call(operation(execution)), 100);
  await tasks.finish(execution);
});

test("HTTP browser identifiers own an execution and survive scoped calls and lease cleanup", async (t) => {
  const h = await harness(t);
  const tasks = h.create();
  const execution = { id: "000102030405060708090a0b0c0d0e0f", spec: SPEC };
  const callId = "101112131415161718191a1b1c1d1e1f";
  await tasks.begin(execution);
  assert.equal(await tasks.call(operation(execution, { execution: { ...execution, callId, test: "HTTP origin" } })), 100);
  assert.ok(h.trace.some((event) => event.id === execution.id && event.callId === callId));
  await tasks.finish(execution);
  const next = scope();
  await tasks.begin(next);
  await tasks.finish(next);
});

test("a live child process owns its database UUID across different application URLs", { timeout: 5000 }, async (t) => {
  const databaseUuid = randomUUID();
  const h = await harness(t, { databaseUuid });
  const source = `
    const { executionTasks } = require(${JSON.stringify(require.resolve("./execution"))});
    const cron = { id: 29, active: true, nextcall: ${JSON.stringify(ORIGINAL_NEXTCALL)} };
    const reminder = { id: 18, enabled: false };
    async function call({ model, method, args }) {
      if (model === "ir.config_parameter" && method === "get_str") return process.env.TEST_DATABASE_UUID;
      if (model === "ir.model.data" && method === "check_object_reference") {
        if (args[1] === "event_task_reminder") return ["mail.message.subtype", 18];
        if (args[1] === "ir_cron_notifications_remind") return ["ir.cron", 29];
      }
      const record = model === "ir.cron" ? cron : model === "mail.message.subtype" ? reminder : null;
      if (record && method === "read") return [{ ...record }];
      if (record && method === "write") { Object.assign(record, args[1]); return true; }
      throw new Error("Unexpected child ORM operation " + model + "." + method);
    }
    const tasks = executionTasks({ call, baseUrl: "http://127.0.0.1:9999", lockDirectory: process.env.TEST_LOCK_DIRECTORY,
      settings: { odooCheckpointSettings: async () => 1, odooRestoreSettings: async () => null } });
    process.on("message", async () => { await tasks.cleanup(); process.disconnect(); });
    tasks.begin({ id: process.env.TEST_RUN_ID, spec: ${JSON.stringify(SPEC)} })
      .then(() => process.send({ ready: true, pid: process.pid }))
      .catch((error) => { console.error(error); process.exitCode = 1; process.disconnect(); });
  `;
  const child = spawn(process.execPath, ["-e", source], {
    env: { ...process.env, TEST_DATABASE_UUID: databaseUuid, TEST_LOCK_DIRECTORY: h.lockDirectory, TEST_RUN_ID: randomUUID() },
    stdio: ["ignore", "pipe", "pipe", "ipc"],
  });
  const exited = once(child, "exit");
  t.after(async () => {
    if (child.exitCode === null && child.signalCode === null) child.kill();
    await exited;
  });
  const [message] = await Promise.race([
    once(child, "message"),
    exited.then(([code]) => {
      throw new Error(`Lease owner exited before readiness (${code})`);
    }),
  ]);
  assert.equal(message.ready, true);
  assert.equal(message.pid, child.pid);
  const contender = h.create();
  await assert.rejects(() => contender.begin(scope()), /owns|active|owned|running|lease|another/i);
  assert.ok(
    h.calls.every(({ method }) => method === "get_str"),
    "a competing process cannot prepare or mutate the database",
  );
  child.send("finish");
  assert.deepEqual(await exited, [0, null]);
  const execution = scope();
  await contender.begin(execution);
  await contender.finish(execution);
});

test("replacing an interrupted execution drains its pending RPC before restoring and granting the new scope", { timeout: 5000 }, async (t) => {
  const h = await harness(t);
  const tasks = h.create();
  const old = scope();
  await tasks.begin(old);
  const entered = deferred();
  const release = deferred();
  h.intercept(
    ({ model }) => model === "medilab.task",
    async () => {
      entered.resolve();
      await release.promise;
      h.settings.set("private.token", "changed by old request");
      return 100;
    },
  );
  const pending = tasks.call(operation(old));
  await entered.promise;
  const next = scope();
  let granted = false;
  const replacement = tasks.begin(next).then(() => {
    granted = true;
  });
  await new Promise(setImmediate);
  assert.equal(granted, false, "a new run cannot restore while the old RPC can still commit");
  await assert.rejects(() => tasks.call(operation(old)), /execution|scope|own/i);
  release.resolve();
  await pending;
  await replacement;
  assert.equal(h.settings.get("private.token"), SECRET);
  const count = h.calls.length;
  await assert.rejects(() => tasks.call(operation(old)), /stale|inactive|execution|scope/i);
  await assert.rejects(() => tasks.finish(old), /stale|inactive|execution|scope/i);
  assert.equal(h.calls.length, count, "a stale token cannot touch the database or finish the new run");
  assert.equal(await tasks.call(operation(next)), 100);
  await tasks.finish(next);
});

test("a drain deadline fails closed until the old request actually completes", { timeout: 5000 }, async (t) => {
  const h = await harness(t);
  const tasks = h.create({ deadlineMs: 1 });
  const old = scope();
  await tasks.begin(old);
  const entered = deferred();
  const release = deferred();
  h.intercept(
    ({ model }) => model === "medilab.task",
    async () => {
      entered.resolve();
      await release.promise;
      return 100;
    },
  );
  const pending = tasks.call(operation(old));
  await entered.promise;
  const next = scope();
  await assert.rejects(() => tasks.begin(next), /unfinished requests/i);
  await assert.rejects(() => tasks.call(operation(old)), /execution|scope|own/i);
  const contender = h.create();
  await assert.rejects(() => contender.begin(scope()), /owns|active|owned|running|lease|another/i);
  assert.equal(h.cron.active, false, "a timed-out drain must retain its paused scheduler and ownership");
  release.resolve();
  await pending;
  await tasks.begin(next);
  await tasks.finish(next);
  assert.equal(h.cron.active, true);
});

for (const active of [false, true]) {
  test(`finish restores reminder and cron active=${active} with its exact original nextcall`, async (t) => {
    const h = await harness(t, { active });
    const tasks = h.create();
    const execution = scope();
    await tasks.begin(execution);
    assert.equal(h.cron.active, false);
    await tasks.call(operation(execution, { model: "ir.cron", method: "method_direct_trigger", args: [[29]] }));
    h.reminder.enabled = true;
    await tasks.finish(execution);
    assert.deepEqual(h.cron, { id: 29, active, nextcall: ORIGINAL_NEXTCALL });
    assert.equal(h.reminder.enabled, false);
  });
}

test("preparing an originally inactive cron resolves its external ID with inactive records included", async (t) => {
  const h = await harness(t, { active: false });
  const tasks = h.create();
  const execution = scope();
  await tasks.begin(execution);
  const lookup = h.calls.find(
    ({ model, method, args }) => model === "ir.model.data" && method === "check_object_reference" && args[1] === "ir_cron_notifications_remind",
  );
  assert.equal(lookup.kwargs.context.active_test, false);
  await tasks.finish(execution);
  assert.equal(h.cron.active, false);
});

test("distinct intentional reminder invocations both reach the server", async (t) => {
  const h = await harness(t);
  const tasks = h.create();
  const execution = scope();
  await tasks.begin(execution);
  const request = { model: "ir.cron", method: "method_direct_trigger", args: [[29]] };
  assert.equal(await tasks.call(operation(execution, request)), true);
  assert.equal(await tasks.call(operation(execution, request)), true);
  assert.equal(h.calls.filter(({ method }) => method === "method_direct_trigger").length, 2);
  await tasks.finish(execution);
});

test("an Odoo cron display_exception result is rejected instead of being reported as successful", async (t) => {
  const h = await harness(t);
  const tasks = h.create();
  const execution = scope();
  await tasks.begin(execution);
  h.intercept(
    ({ model, method }) => model === "ir.cron" && method === "method_direct_trigger",
    () => ({
      type: "ir.actions.client",
      tag: "display_exception",
      params: { message: SECRET },
    }),
  );
  await assert.rejects(
    () => tasks.call(operation(execution, { model: "ir.cron", method: "method_direct_trigger", args: [[29]] })),
    (error) => error instanceof Error && !error.message.includes(SECRET),
  );
  await tasks.finish(execution);
  assert.deepEqual(h.cron, { id: 29, active: true, nextcall: ORIGINAL_NEXTCALL });
});

test("a failed checkpoint restoration keeps the application lease and remains recoverable", async (t) => {
  const h = await harness(t);
  const tasks = h.create();
  const contender = h.create();
  const execution = scope();
  await tasks.begin(execution);
  h.settings.set("private.token", "modified");
  h.failRestore(new Error("Controlled settings restoration failure"));
  await assert.rejects(() => tasks.finish(execution));
  assert.equal(h.checkpoints.size, 1);
  await assert.rejects(() => contender.begin(scope()), /active|owned|running|lease|another/i);
  await tasks.finish(execution);
  assert.equal(h.settings.get("private.token"), SECRET);
  assert.equal(h.checkpoints.size, 0);
  assert.equal(h.cron.active, true);
  assert.equal(h.cron.nextcall, ORIGINAL_NEXTCALL);
  const recovered = scope();
  await contender.begin(recovered);
  await contender.finish(recovered);
});

test("an ordinary operation failure restores the original scheduler state during cleanup", async (t) => {
  const h = await harness(t);
  const tasks = h.create();
  const execution = scope();
  await tasks.begin(execution);
  h.intercept(
    ({ model }) => model === "medilab.task",
    () => {
      throw new Error("Controlled operation failure");
    },
  );
  await assert.rejects(() => tasks.call(operation(execution)), /Controlled operation failure/);
  await tasks.cleanup();
  assert.deepEqual(h.cron, { id: 29, active: true, nextcall: ORIGINAL_NEXTCALL });
});

test("recovery releases only bookings and manual tasks created successfully by its own execution", async (t) => {
  const h = await harness(t);
  const tasks = h.create();
  const execution = scope();
  await tasks.begin(execution);
  await tasks.call(operation(execution, { model: "medilab.test.request" }));
  h.fixtures.bookingActive = true;
  await tasks.call(operation(execution));
  h.intercept(
    ({ model, method }) => model === "medilab.test.request" && method === "create",
    () => {
      throw new Error("Controlled create refusal");
    },
  );
  await assert.rejects(() => tasks.call(operation(execution, { model: "medilab.test.request" })), /Controlled create refusal/);
  await tasks.finish(execution);
  assert.deepEqual(
    h.calls.filter(({ method }) => method === "action_cancel").map(({ model, args }) => ({ model, args })),
    [
      { model: "medilab.machine.booking", args: [[300]] },
      { model: "medilab.task", args: [[100]] },
    ],
  );
});

test("failed fixture cancellation retains ownership and every restoration checkpoint for retry", async (t) => {
  const h = await harness(t);
  const tasks = h.create();
  const execution = scope();
  await tasks.begin(execution);
  await tasks.call(operation(execution));
  h.intercept(
    ({ model, method }) => model === "medilab.task" && method === "action_cancel",
    () => {
      throw new Error("Controlled cancellation failure");
    },
  );
  await assert.rejects(() => tasks.finish(execution), /could not be restored/i);
  assert.equal(h.checkpoints.size, 1);
  assert.equal(h.cron.active, false);
  const contender = h.create();
  await assert.rejects(() => contender.begin(scope()), /owns|active|owned|running|lease|another/i);
  await tasks.cleanup();
  assert.equal(h.checkpoints.size, 0);
  assert.equal(h.cron.active, true);
  const next = scope();
  await contender.begin(next);
  await contender.finish(next);
});

for (const model of ["medilab.task", "medilab.machine.booking"]) {
  test(`a no-op ${model} cancellation cannot release the lease with active fixture state`, async (t) => {
    const h = await harness(t);
    const tasks = h.create();
    const execution = scope();
    await tasks.begin(execution);
    await tasks.call(operation(execution, { model: model === "medilab.task" ? model : "medilab.test.request" }));
    if (model === "medilab.machine.booking") h.fixtures.bookingActive = true;
    h.intercept(
      (request) => request.model === model && request.method === "action_cancel",
      () => true,
    );
    await assert.rejects(() => tasks.finish(execution), /could not be restored/i);
    assert.equal(h.checkpoints.size, 1);
    const contender = h.create();
    await assert.rejects(() => contender.begin(scope()), /owns|active|owned|running|lease|another/i);
    await tasks.cleanup();
    assert.equal(h.fixtures.taskActive, false);
    assert.equal(h.fixtures.bookingActive, false);
    assert.equal(h.checkpoints.size, 0);
    assert.equal(h.cron.active, true);
  });
}

test("a preparation failure rolls back a pause that may already have committed", async (t) => {
  const h = await harness(t);
  const tasks = h.create();
  h.intercept(
    ({ model, method, args }) => model === "ir.cron" && method === "write" && args[1].active === false,
    () => {
      h.cron.active = false;
      throw new Error("Controlled lost pause response");
    },
  );
  await assert.rejects(() => tasks.begin(scope()), /could not be prepared/i);
  assert.deepEqual(h.cron, { id: 29, active: true, nextcall: ORIGINAL_NEXTCALL });
  assert.equal(h.reminder.enabled, false);
  assert.equal(h.checkpoints.size, 0);
  const contender = h.create();
  const execution = scope();
  await contender.begin(execution);
  await contender.finish(execution);
});

test("failed preparation recovery retains its lease and checkpoint for a later cleanup", async (t) => {
  const h = await harness(t);
  const tasks = h.create();
  h.intercept(isPause, () => {
    h.cron.active = false;
    throw new Error("Controlled lost pause response");
  });
  h.failRestore(new Error("Controlled recovery failure"));
  await assert.rejects(() => tasks.begin(scope()), /could not be prepared/i);
  assert.equal(h.checkpoints.size, 1);
  const contender = h.create();
  await assert.rejects(() => contender.begin(scope()), /owns|active|owned|running|lease|another/i);
  await tasks.cleanup();
  assert.equal(h.checkpoints.size, 0);
  assert.equal(h.cron.active, true);
  const execution = scope();
  await contender.begin(execution);
  await contender.finish(execution);
});

test("failed cron restoration retains the lease and retries only unfinished cleanup stages", async (t) => {
  const h = await harness(t);
  const tasks = h.create();
  const contender = h.create();
  const execution = scope();
  await tasks.begin(execution);
  h.intercept(
    ({ model, method, args }) => model === "ir.cron" && method === "write" && "nextcall" in args[1],
    () => {
      throw new Error("Controlled scheduler restoration failure");
    },
  );
  await assert.rejects(() => tasks.finish(execution), /could not be restored/i);
  await assert.rejects(() => contender.begin(scope()), /owns|active|owned|running|lease|another/i);
  await tasks.cleanup();
  assert.deepEqual(h.cron, { id: 29, active: true, nextcall: ORIGINAL_NEXTCALL });
  assert.equal(h.checkpoints.size, 0);
  const next = scope();
  await contender.begin(next);
  await contender.finish(next);
});

test("a scoped checkpoint cannot be restored by a later execution", async (t) => {
  const h = await harness(t);
  const tasks = h.create();
  const old = scope();
  await tasks.begin(old);
  const checkpoint = await tasks.checkpoint(operation(old));
  const next = scope();
  await tasks.begin(next);
  h.settings.set("private.token", "new execution owns this value");
  await assert.rejects(() => tasks.restore({ checkpoint, execution: { ...old, callId: randomUUID() } }), /execution|scope|own/i);
  assert.equal(h.settings.get("private.token"), "new execution owns this value");
  await tasks.finish(next);
});

test("a successful explicit restoration consumes only its own checkpoint", async (t) => {
  const h = await harness(t);
  const tasks = h.create();
  const execution = scope();
  await tasks.begin(execution);
  const checkpoint = await tasks.checkpoint(operation(execution));
  h.settings.set("private.token", "changed");
  await tasks.restore({ checkpoint, execution: { ...execution, callId: randomUUID() } });
  assert.equal(h.settings.get("private.token"), SECRET);
  assert.equal(h.checkpoints.size, 1, "outer execution checkpoint remains available for final restoration");
  await tasks.finish(execution);
  assert.equal(h.checkpoints.size, 0);
});

const CRON_WRITE_LOCK =
  "Record cannot be modified right now: This cron task is currently being executed and may not be modified Please try again in a few minutes";
const isPause = ({ model, method, args }) => model === "ir.cron" && method === "write" && args[1].active === false && !("nextcall" in args[1]);

test("nested checkpoints restore newest first and a failed step retains the lease and older snapshots", { timeout: 5000 }, async (t) => {
  const h = await harness(t);
  const started = deferred();
  const release = deferred();
  const restored = [];
  let newest;
  let failing;
  let blocked = false;
  const tasks = h.create({
    settings: {
      ...h.settingsTasks,
      async odooRestoreSettings(payload) {
        restored.push(payload.checkpoint);
        if (payload.checkpoint === newest && !blocked) {
          blocked = true;
          started.resolve();
          await release.promise;
        }
        if (payload.checkpoint === failing) {
          failing = undefined;
          throw new Error("Controlled nested checkpoint failure");
        }
        return h.settingsTasks.odooRestoreSettings(payload);
      },
    },
  });
  const execution = scope();
  await tasks.begin(execution);
  const [outer] = h.checkpoints.keys();
  h.settings.set("private.token", "before older checkpoint");
  const older = await tasks.checkpoint(operation(execution));
  h.settings.set("private.token", "before newest checkpoint");
  newest = await tasks.checkpoint(operation(execution));
  h.settings.set("private.token", "changed in nested test");
  failing = older;
  const failed = assert.rejects(() => tasks.finish(execution), /could not be restored/i);
  try {
    await started.promise;
    assert.deepEqual(restored, [newest], "older snapshots cannot start while the newest restore is pending");
    assert.equal(h.checkpoints.size, 3);
    assert.equal(h.cron.active, false);
  } finally {
    release.resolve();
    await failed;
  }
  assert.deepEqual(restored, [newest, older]);
  assert.deepEqual([...h.checkpoints.keys()], [outer, older]);
  assert.equal(h.settings.get("private.token"), "before newest checkpoint");
  assert.equal(h.cron.active, false);
  const contender = h.create();
  await assert.rejects(() => contender.begin(scope()), /another.*execution/i);

  await tasks.finish(execution);

  assert.deepEqual(restored, [newest, older, older, outer]);
  assert.equal(h.settings.get("private.token"), SECRET);
  assert.equal(h.checkpoints.size, 0);
  assert.deepEqual(h.cron, { id: 29, active: true, nextcall: ORIGINAL_NEXTCALL });
  const next = scope();
  await contender.begin(next);
  await contender.finish(next);
});

test("only the exact typed cron-write lock refusal receives a bounded retry", async (t) => {
  const h = await harness(t);
  const tasks = h.create({ deadlineMs: 1000 });
  const execution = scope();
  h.intercept(isPause, () => {
    throw Object.assign(new Error(CRON_WRITE_LOCK), { name: "odoo.exceptions.UserError" });
  });
  await tasks.begin(execution);
  assert.equal(h.calls.filter(isPause).length, 2);
  await tasks.finish(execution);
  for (const [name, message] of [
    ["odoo.exceptions.AccessError", CRON_WRITE_LOCK],
    ["odoo.exceptions.UserError", "You are not allowed to run this job."],
    ["Error", CRON_WRITE_LOCK],
  ]) {
    h.intercept(isPause, () => {
      throw Object.assign(new Error(message), { name });
    });
    const before = h.calls.filter(isPause).length;
    await assert.rejects(() => tasks.begin(scope()), /could not be prepared/i);
    assert.equal(h.calls.filter(isPause).length, before + 1, "unrelated failures must not be retried");
    assert.equal(h.cron.active, true);
  }
});

test("manual cron refusal is a business failure rather than a request to replay the operation", async (t) => {
  const h = await harness(t);
  const tasks = h.create();
  const execution = scope();
  await tasks.begin(execution);
  const isTrigger = ({ model, method }) => model === "ir.cron" && method === "method_direct_trigger";
  const error = Object.assign(new Error("Job 'Notification reminders' already executing"), { name: "odoo.exceptions.UserError" });
  h.intercept(isTrigger, () => {
    throw error;
  });
  await assert.rejects(
    () => tasks.call(operation(execution, { model: "ir.cron", method: "method_direct_trigger", args: [[29]] })),
    (actual) => actual === error,
  );
  assert.equal(h.calls.filter(isTrigger).length, 1);
  await tasks.finish(execution);
});

test("a permanently locked pause stops within the configured budget and restores original state", async (t) => {
  const h = await harness(t);
  const tasks = h.create({ deadlineMs: 1 });
  let attempts = 0;
  const busy = () => {
    h.intercept(isPause, () => {
      attempts += 1;
      busy();
      throw Object.assign(new Error(CRON_WRITE_LOCK), { name: "odoo.exceptions.UserError" });
    });
  };
  busy();
  await assert.rejects(() => tasks.begin(scope()), /could not be prepared/i);
  assert.ok(attempts >= 1 && attempts <= 2, "bounded lock waiting must not become an unlimited business retry");
  assert.equal(h.cron.active, true);
  assert.equal(h.cron.nextcall, ORIGINAL_NEXTCALL);
});

test("trace metadata contains call identifiers without settings, values or session cookies", async (t) => {
  const h = await harness(t);
  const tasks = h.create();
  const execution = scope();
  await tasks.begin(execution);
  const payload = operation(execution, { args: [{ name: SECRET, cookie: "FAKE-COOKIE-NOT-FOR-TRACE" }] });
  await tasks.call(payload);
  h.intercept(
    ({ model }) => model === "medilab.task",
    () => {
      throw new Error(SECRET);
    },
  );
  await assert.rejects(
    () => tasks.call(operation(execution)),
    (error) => error.message === SECRET,
  );
  await tasks.finish(execution);
  const serialized = JSON.stringify(h.trace);
  assert.ok(h.trace.length > 0, "lifecycle and RPC metadata are traceable");
  assert.ok(serialized.includes(payload.execution.callId));
  assert.equal(serialized.includes(SECRET), false);
  assert.equal(serialized.includes("FAKE-COOKIE-NOT-FOR-TRACE"), false);
});
