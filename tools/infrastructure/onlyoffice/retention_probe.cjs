"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");

const BINARY = "/var/www/onlyoffice/documentserver/server/DocService/docservice";
const BINARY_SHA256 = "556df4aab7b1a87123046a4459baee34e60f57deaf7bcd189bccd6f271bd8fcb";
const COMMON = "/snapshot/server/Common/sources/";
const SERVICE = "/snapshot/server/DocService/sources/";
const DAY_SECONDS = 86400;
let stage = "runtime-guard";

async function main() {
  assert.equal(process.env.MEDILAB_ONLYOFFICE_RETENTION_FIXTURE, "isolated-empty");
  assert.equal(process.execPath, BINARY);
  assert(process.pkg);
  assert.equal(crypto.createHash("sha256").update(fs.readFileSync(BINARY)).digest("hex"), BINARY_SHA256);
  stage = "load-config";
  const config = require(COMMON + "moduleReloader.js").requireConfigWithRuntime();
  stage = "policy-guard";
  assert.equal(config.get("services.CoAuthoring.expire.files"), 7 * DAY_SECONDS);
  assert.equal(config.get("services.CoAuthoring.sql.tableResult"), "task_result");
  assert.equal(config.get("services.CoAuthoring.sql.tableChanges"), "doc_changes");
  assert.equal(config.get("storage.name"), "storage-fs");
  stage = "load-modules";
  const Context = require(COMMON + "operationContext.js").Context;
  const storage = require(COMMON + "storage/storage-base.js");
  const tasks = require(SERVICE + "taskresult.js");
  const sql = require(SERVICE + "databaseConnectors/baseConnector.js");
  const canvas = require(SERVICE + "canvasservice.js");
  const gc = require(SERVICE + "gc.js");
  const ctx = new Context();
  await ctx.initTenantCache();
  stage = "context-policy-guard";
  assert.equal(ctx.getCfg("services.CoAuthoring.expire.files", 0), 7 * DAY_SECONDS);

  // Refuse existing eligible or changed task records before sweeping this disposable native process.
  stage = "empty-fixture-guard";
  assert.equal((await tasks.getExpired(ctx, 1, 0)).length, 0);
  assert.equal((await sql.getDocumentsWithChanges(ctx)).length, 0);
  const prefix = "medilab_retention_" + crypto.randomBytes(12).toString("hex");
  const keys = {young: prefix + "_2d", expired: prefix + "_8d"};
  const bytes = Buffer.from("MediLab isolated native cache retention fixture\n");
  const sha256 = crypto.createHash("sha256").update(bytes).digest("hex");
  stage = "create-fixtures";
  const NativeDate = Date;
  for (const [name, ageDays] of [["young", 2], ["expired", 8]]) {
    const ageMilliseconds = ageDays * DAY_SECONDS * 1000;
    // The Community adapter assigns its own timestamp. Age only this disposable process's fixture creation.
    global.Date = class FixtureDate extends NativeDate {
      constructor(...args) {
        super(...(args.length ? args : [NativeDate.now() - ageMilliseconds]));
      }
      static now() { return NativeDate.now() - ageMilliseconds; }
    };
    try {
      const task = new tasks.TaskResultData();
      task.key = keys[name];
      task.tenant = ctx.tenant;
      task.completeDefaults();
      assert.equal((await tasks.select(ctx, task.key)).length, 0);
      await tasks.upsert(ctx, task);
    } finally {
      global.Date = NativeDate;
    }
    const row = (await tasks.select(ctx, keys[name]))[0];
    const actualAge = NativeDate.now() - new NativeDate(row.last_open_date).getTime();
    assert.ok(Math.abs(actualAge - ageMilliseconds) < 5000);
    await storage.putObject(ctx, keys[name] + "/probe.bin", bytes, bytes.length);
  }
  assert.equal(Date, NativeDate);
  const selected = await tasks.getExpired(ctx, 100, ctx.getCfg("services.CoAuthoring.expire.files", 0));
  stage = "expiration-selection";
  assert.deepEqual(selected.map(row => row.id), [keys.expired]);
  // Use the worker's configured duration; no shortened expiration or clock override is supplied.
  stage = "native-gc";
  await gc.checkFileExpire();
  const young = await tasks.select(ctx, keys.young);
  const expired = await tasks.select(ctx, keys.expired);
  stage = "verify-retention";
  assert.equal(young.length, 1);
  assert.equal(expired.length, 0);
  const retained = await storage.getObject(ctx, keys.young + "/probe.bin");
  assert.equal(crypto.createHash("sha256").update(retained).digest("hex"), sha256);
  await assert.rejects(storage.getObject(ctx, keys.expired + "/probe.bin"), {code: "ENOENT"});

  stage = "cleanup-owned-fixtures";
  assert.equal(await canvas.cleanupCache(ctx, keys.young), true);
  assert.equal((await tasks.getExpired(ctx, 1, 0)).length, 0);
  assert.equal((await sql.getDocumentsWithChanges(ctx)).length, 0);
  process.stdout.write(JSON.stringify({
    status: "PASS",
    method: "aged-record native-GC fixture",
    timestampMethod: "process-local Date override during fixture creation; restored before native GC",
    binarySha256: BINARY_SHA256,
    expire_files: 7 * DAY_SECONDS,
    younger: {ageDays: 2, rowRetained: true, bytesRetained: true, sha256},
    expired: {ageDays: 8, rowRemoved: true, bytesRemoved: true},
    fixturesCleaned: true,
    elapsedSevenDays: false,
  }) + "\n");
}

const deadline = setTimeout(() => {
  process.stderr.write("ONLYOFFICE retention probe exceeded its 30-second deadline.\n");
  process.exit(124);
}, 30000);
main().then(() => {
  clearTimeout(deadline);
  process.exit(0);
}).catch(error => {
  clearTimeout(deadline);
  const kind = ["AssertionError", "TypeError", "Error"].includes(error.name) ? error.name : "OtherError";
  process.stderr.write(JSON.stringify({status: "FAIL", stage, kind}) + "\n");
  process.exit(1);
});
