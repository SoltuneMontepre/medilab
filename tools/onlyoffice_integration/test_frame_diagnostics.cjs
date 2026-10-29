"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {collectFrameDiagnostics} = require("./frame_diagnostics.cjs");

test("independent frame reads preserve frame order and finish before cleanup", async () => {
  const pending = [];
  const page = {frames: () => [0, 1, 2].map(index => ({
    evaluate: () => new Promise((resolve, reject) => { pending[index] = {resolve, reject}; }),
  }))};
  let complete = false;
  const result = collectFrameDiagnostics(page).then(frames => { complete = true; return frames; });
  assert.equal(pending.length, 3);
  pending[2].resolve([{tag: "TEXTAREA", id: "last", editable: null}]);
  pending[1].reject(new Error("Frame detached"));
  await Promise.resolve();
  assert.equal(complete, false);
  pending[0].resolve([{tag: "CANVAS", id: "first", editable: null}]);
  assert.deepEqual(await result, [[{tag: "CANVAS", id: "first", editable: null}], [],
    [{tag: "TEXTAREA", id: "last", editable: null}]]);
  assert.equal(complete, true);
});

test("frame diagnostics expose only the bounded structural fields", async () => {
  const original = global.document;
  global.document = {querySelectorAll(selector) {
    assert.equal(selector, "canvas, textarea, [contenteditable]");
    return Array.from({length: 30}, () => ({tagName: "CANVAS", id: "editor", value: "private",
      getAttribute(name) { assert.equal(name, "contenteditable"); return "true"; }}));
  }};
  try {
    const frames = await collectFrameDiagnostics({frames: () => [{evaluate: async callback => callback()}]});
    assert.equal(frames[0].length, 20);
    assert.deepEqual(frames[0][0], {tag: "CANVAS", id: "editor", editable: "true"});
  } finally {
    if (original === undefined) delete global.document;
    else global.document = original;
  }
});
