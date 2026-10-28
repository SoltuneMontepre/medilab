"use strict";

const assert = require("node:assert/strict");
const DAY_SECONDS = 86400;

async function createAgedFixture({tasks, storage, ctx, key, ageDays, bytes}) {
  const NativeDate = Date;
  const ageMilliseconds = ageDays * DAY_SECONDS * 1000;
  // The native adapter owns the timestamp. Override only this fixture's creation and always restore it.
  global.Date = class FixtureDate extends NativeDate {
    constructor(...args) {
      super(...(args.length ? args : [NativeDate.now() - ageMilliseconds]));
    }
    static now() { return NativeDate.now() - ageMilliseconds; }
  };
  try {
    const task = new tasks.TaskResultData();
    task.key = key;
    task.tenant = ctx.tenant;
    task.completeDefaults();
    assert.equal((await tasks.select(ctx, key)).length, 0);
    await tasks.upsert(ctx, task);
  } finally {
    global.Date = NativeDate;
  }
  const row = (await tasks.select(ctx, key))[0];
  const actualAge = NativeDate.now() - new NativeDate(row.last_open_date).getTime();
  assert.ok(Math.abs(actualAge - ageMilliseconds) < 5000);
  await storage.putObject(ctx, key + "/probe.bin", bytes, bytes.length);
}

module.exports = {createAgedFixture};
