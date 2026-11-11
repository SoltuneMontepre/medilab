"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {visitEditorsInOrder} = require("./editor_lifecycle.cjs");

test("participant sessions open, destroy and close in order with only one active", async () => {
  const calls = [];
  let active = false;
  await visitEditorsInOrder(["one", "two", "three"], async url => {
    assert.equal(active, false);
    active = true;
    calls.push("open:" + url);
    return {
      async evaluate() { assert.equal(active, true); calls.push("destroy:" + url); },
      async close() { calls.push("close:" + url); active = false; },
    };
  });
  assert.equal(active, false);
  assert.deepEqual(calls, ["open:one", "destroy:one", "close:one", "open:two", "destroy:two", "close:two",
    "open:three", "destroy:three", "close:three"]);
});

test("a failed participant prevents later sessions and preserves the failure", async () => {
  const failure = new Error("Destroy failed");
  const calls = [];
  await assert.rejects(visitEditorsInOrder(["one", "two"], async url => {
    calls.push(url);
    return {async evaluate() { throw failure; }, async close() { assert.fail("Closure must follow destruction"); }};
  }), error => error === failure);
  assert.deepEqual(calls, ["one"]);
});
