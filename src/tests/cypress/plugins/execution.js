const { createHash } = require("node:crypto");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");

const ADMINISTRATOR = "demo.administrator";
const OWNERSHIP_ERROR = "This test execution does not own the application.";
const LEASE_ERROR = "Another test execution owns this database on this host.";
const CRON_LOCK_MESSAGE =
  "Record cannot be modified right now: This cron task is currently being executed and may not be modified Please try again in a few minutes";

// Ownership is host-local. Separate hosts must use separate test databases; interrupted HTTP requests cannot be cancelled here.
function executionTasks({
  call: rawCall,
  settings,
  baseUrl,
  lockDirectory = path.join(os.tmpdir(), "medilab-cypress"),
  trace = () => {},
  deadlineMs = 10000,
}) {
  let current;
  let lifecycle = Promise.resolve();

  function serial(operation) {
    const result = lifecycle.then(operation);
    lifecycle = result.catch(() => {});
    return result;
  }

  function owns(execution) {
    if (!current || !current.open || execution?.id !== current.id || execution.spec !== current.spec) {
      throw new Error(OWNERSHIP_ERROR);
    }
    return current;
  }

  async function rpc(model, method, args, kwargs = {}) {
    return rawCall({ login: ADMINISTRATOR, model, method, args, kwargs });
  }

  async function reference(name) {
    const [, id] = await rpc("ir.model.data", "check_object_reference", ["sol_laboratory", name], { context: { active_test: false } });
    return id;
  }

  async function read(model, id, fields) {
    const [record] = await rpc(model, "read", [[id], fields]);
    if (!record) throw new Error("The saved test record is unavailable.");
    return record;
  }

  async function cronWrite(id, values) {
    const until = Date.now() + deadlineMs;
    for (;;) {
      try {
        return await rpc("ir.cron", "write", [[id], values]);
      } catch (error) {
        const locked =
          error.name === "odoo.exceptions.UserError" && (error.message === CRON_LOCK_MESSAGE || error.message.endsWith(`: ${CRON_LOCK_MESSAGE}`));
        if (!locked || Date.now() >= until) throw error;
        await new Promise((resolve) => setTimeout(resolve, Math.min(100, until - Date.now())));
      }
    }
  }

  async function lease(scope) {
    const uuid = await rpc("ir.config_parameter", "get_str", ["database.uuid"]);
    if (typeof uuid !== "string" || !uuid) throw new Error("The test database identity is unavailable.");
    const key = createHash("sha256").update(uuid).digest("hex");
    await fs.mkdir(lockDirectory, { recursive: true, mode: 0o700 });
    const directory = path.join(lockDirectory, key);
    try {
      await fs.mkdir(directory, { mode: 0o700 });
    } catch (error) {
      if (error.code === "EEXIST") throw new Error(LEASE_ERROR);
      throw error;
    }
    try {
      await fs.writeFile(path.join(directory, "owner.json"), JSON.stringify({ pid: process.pid, runId: scope.id }), { flag: "wx", mode: 0o600 });
    } catch (error) {
      await fs.rm(directory, { recursive: true, force: true });
      throw error;
    }
    scope.directory = directory;
  }

  async function release(scope) {
    if (!scope.directory) return;
    const owner = JSON.parse(await fs.readFile(path.join(scope.directory, "owner.json"), "utf8"));
    if (owner.pid !== process.pid || owner.runId !== scope.id) throw new Error(OWNERSHIP_ERROR);
    await fs.unlink(path.join(scope.directory, "owner.json"));
    await fs.rmdir(scope.directory);
    scope.directory = undefined;
  }

  async function drain(scope) {
    let timeout;
    try {
      await Promise.race([
        Promise.allSettled([...scope.pending]),
        new Promise((_, reject) => {
          timeout = setTimeout(() => reject(new Error("The previous test execution still has unfinished requests.")), deadlineMs);
        }),
      ]);
    } finally {
      clearTimeout(timeout);
    }
  }

  async function cancelOwned(scope) {
    if (scope.requests.size) {
      const domain = [
        ["sample_test_id.sample_id.request_id", "in", [...scope.requests]],
        ["status", "in", ["queued", "scheduled"]],
      ];
      const ids = await rpc("medilab.machine.booking", "search", [domain]);
      if (ids.length) await rpc("medilab.machine.booking", "action_cancel", [ids]);
      if (await rpc("medilab.machine.booking", "search_count", [domain])) throw new Error("Owned reservations remain active.");
    }
    if (scope.tasks.size) {
      const domain = [
        ["id", "in", [...scope.tasks]],
        ["document_model", "=", false],
        ["status", "not in", ["done", "cancelled"]],
      ];
      const ids = await rpc("medilab.task", "search", [domain]);
      if (ids.length) await rpc("medilab.task", "action_cancel", [ids]);
      if (await rpc("medilab.task", "search_count", [domain])) throw new Error("Owned tasks remain unfinished.");
    }
  }

  async function restoreScope(scope) {
    if (!scope.done.fixtures) {
      await cancelOwned(scope);
      scope.done.fixtures = true;
    }
    if (!scope.done.settings) {
      for (const checkpoint of [...scope.checkpoints].reverse()) {
        await settings.odooRestoreSettings({ checkpoint });
        scope.checkpoints.delete(checkpoint);
      }
      if (scope.outer !== undefined) await settings.odooRestoreSettings({ checkpoint: scope.outer });
      scope.done.settings = true;
    }
    if (!scope.done.reminder && scope.reminder) {
      const { id, enabled } = scope.reminder;
      await rpc("mail.message.subtype", "write", [[id], { enabled }]);
      const restored = await read("mail.message.subtype", id, ["enabled"]);
      if (restored.enabled !== enabled) throw new Error("The reminder event could not be verified.");
      scope.done.reminder = true;
    }
    if (!scope.done.cron && scope.cron) {
      const { id, active, nextcall } = scope.cron;
      await cronWrite(id, { active, nextcall });
      const restored = await read("ir.cron", id, ["active", "nextcall"]);
      if (restored.active !== active || restored.nextcall !== nextcall) throw new Error("The reminder schedule could not be verified.");
      scope.done.cron = true;
    }
    await release(scope);
    if (current === scope) current = undefined;
  }

  async function close(scope) {
    scope.open = false;
    trace({ id: scope.id, spec: scope.spec, phase: "closing", at: new Date().toISOString() });
    await drain(scope);
    try {
      await restoreScope(scope);
      trace({ id: scope.id, spec: scope.spec, phase: "restored", at: new Date().toISOString() });
    } catch {
      throw new Error("The test execution could not be restored.");
    }
  }

  function begin({ id, spec }) {
    if (typeof id !== "string" || !id || typeof spec !== "string" || !spec) return Promise.reject(new Error(OWNERSHIP_ERROR));
    if (current) current.open = false;
    return serial(async () => {
      if (current) await close(current);
      const scope = { id, spec, open: false, pending: new Set(), requests: new Set(), tasks: new Set(), checkpoints: new Set(), done: {} };
      try {
        await lease(scope);
      } catch (error) {
        if (scope.directory) current = scope;
        if (error.message === LEASE_ERROR) throw new Error(LEASE_ERROR);
        throw new Error("The test execution could not be prepared.");
      }
      current = scope;
      try {
        scope.outer = await settings.odooCheckpointSettings({ login: ADMINISTRATOR });
        scope.reminder = await read("mail.message.subtype", await reference("event_task_reminder"), ["enabled"]);
        scope.cron = await read("ir.cron", await reference("ir_cron_notifications_remind"), ["active", "nextcall"]);
        await cronWrite(scope.cron.id, { active: false });
        const paused = await read("ir.cron", scope.cron.id, ["active"]);
        if (paused.active !== false) throw new Error("The reminder schedule could not be paused.");
        scope.open = true;
        trace({ id, spec, phase: "prepared", at: new Date().toISOString() });
        return null;
      } catch {
        try {
          await restoreScope(scope);
        } catch {
          // Keep the lease and private checkpoint so the next begin can retry recovery.
        }
        throw new Error("The test execution could not be prepared.");
      }
    });
  }

  function finish({ id }) {
    if (!current || current.id !== id) return Promise.reject(new Error(OWNERSHIP_ERROR));
    const scope = current;
    scope.open = false;
    return serial(async () => {
      if (current !== scope) throw new Error(OWNERSHIP_ERROR);
      await close(scope);
      return null;
    });
  }

  function dispatch(payload, operation) {
    let scope;
    try {
      if (current || payload.execution) scope = owns(payload.execution);
    } catch (error) {
      return Promise.reject(error);
    }
    if (!scope) return operation();
    const { execution, ...request } = payload;
    const event = { id: scope.id, spec: scope.spec, callId: execution.callId, test: execution.test, model: request.model, method: request.method };
    const pending = Promise.resolve().then(async () => {
      trace({ ...event, phase: "start", at: new Date().toISOString() });
      try {
        const result = await operation(scope, request);
        trace({ ...event, phase: "end", outcome: "fulfilled", at: new Date().toISOString() });
        return result;
      } catch (error) {
        trace({ ...event, phase: "end", outcome: "rejected", at: new Date().toISOString() });
        throw error;
      }
    });
    scope.pending.add(pending);
    pending.then(
      () => scope.pending.delete(pending),
      () => scope.pending.delete(pending),
    );
    return pending;
  }

  function call(payload) {
    return dispatch(payload, async (scope, request = payload) => {
      const result = await rawCall(request);
      if (scope && request.model === "ir.cron" && request.method === "method_direct_trigger" && result !== true) {
        throw new Error("The reminder job did not finish successfully.");
      }
      if (scope && request.method === "create") {
        const ids = Array.isArray(result) ? result : [result];
        const owned = request.model === "medilab.test.request" ? scope.requests : request.model === "medilab.task" ? scope.tasks : null;
        if (owned) ids.filter((id) => Number.isInteger(id) && id > 0).forEach((id) => owned.add(id));
      }
      return result;
    });
  }

  function checkpoint(payload) {
    return dispatch(payload, async (scope, request = payload) => {
      const id = await settings.odooCheckpointSettings(request);
      if (scope) scope.checkpoints.add(id);
      return id;
    });
  }

  function restore(payload) {
    return dispatch(payload, async (scope, request = payload) => {
      if (scope && !scope.checkpoints.has(request.checkpoint)) throw new Error(OWNERSHIP_ERROR);
      const result = await settings.odooRestoreSettings(request);
      if (scope) scope.checkpoints.delete(request.checkpoint);
      return result;
    });
  }

  function cleanup() {
    if (current) current.open = false;
    return serial(async () => {
      if (current) await close(current);
      return null;
    });
  }

  return { begin, finish, call, checkpoint, restore, cleanup };
}

module.exports = { executionTasks };
