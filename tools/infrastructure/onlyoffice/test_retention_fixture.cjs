"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {createAgedFixture} = require("./retention_fixture.cjs");

const NativeDate = Date;
const ctx = {tenant: "fixture"};
const bytes = Buffer.from("immutable fixture bytes");

function fixture(failure) {
  const rows = new Map();
  const calls = [];
  const tasks = {
    TaskResultData: class { completeDefaults() { this.status = "fixture"; } },
    async select(context, key) {
      assert.equal(context, ctx);
      calls.push("select:" + key);
      if (failure === "select") throw new Error("selection refused");
      return rows.has(key) ? [rows.get(key)] : [];
    },
    async upsert(context, task) {
      assert.equal(context, ctx);
      assert.notEqual(Date, NativeDate);
      assert.equal(task.tenant, ctx.tenant);
      assert.equal(task.status, "fixture");
      if (failure === "upsert") throw new Error("write refused");
      rows.set(task.key, {last_open_date: new Date()});
      calls.push("upsert:" + task.key);
    },
  };
  const storage = {async putObject(context, key, value, length) {
    assert.equal(Date, NativeDate);
    assert.equal(context, ctx);
    assert.equal(value, bytes);
    assert.equal(length, bytes.length);
    calls.push("put:" + key);
    if (failure === "storage") throw new Error("storage refused");
  }};
  return {tasks, storage, ctx, bytes, rows, calls};
}

test("young and expired fixtures finish in order with the native clock restored between them", async () => {
  const f = fixture();
  await createAgedFixture({...f, key: "young", ageDays: 2});
  assert.equal(Date, NativeDate);
  await createAgedFixture({...f, key: "expired", ageDays: 8});
  assert.equal(Date, NativeDate);
  assert.deepEqual(f.calls, ["select:young", "upsert:young", "select:young", "put:young/probe.bin",
    "select:expired", "upsert:expired", "select:expired", "put:expired/probe.bin"]);
  assert.ok(f.rows.get("young").last_open_date > f.rows.get("expired").last_open_date);
});

for (const failure of ["select", "upsert", "storage"]) {
  test(`the native clock is restored when ${failure} fails`, async () => {
    const f = fixture(failure);
    await assert.rejects(createAgedFixture({...f, key: "failed", ageDays: 8}), /refused/);
    assert.equal(Date, NativeDate);
    if (failure !== "storage") assert.equal(f.calls.some(call => call.startsWith("put:")), false);
  });
}
