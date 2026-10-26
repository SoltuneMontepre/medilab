"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const Module = require("node:module");
const path = require("node:path");
const test = require("node:test");

const SIGNING_SOURCE = path.resolve(__dirname, "../../../infra/cluster/onlyoffice/callback-signing.cjs");
const { install } = require(SIGNING_SOURCE);
const DOCS = "/snapshot/server/DocService/sources/DocsCoServer.js";
const COMMON = "/snapshot/server/Common/sources/";
const SECRET = "callback-signing-fixture-01234567890123456789";
const FIELDS = {
  key: "document-key",
  status: 2,
  url: "https://docs.example/cache/output.docx?md5=signed",
  users: ["7"],
  actions: [{type: 0, userid: "7"}],
  changesurl: "https://docs.example/cache/changes.zip?md5=signed",
  history: {changes: [{user: {id: "7", name: "Editor"}}]},
};

function encode(payload, secret) {
  const header = Buffer.from(JSON.stringify({alg: "HS256", typ: "JWT"})).toString("base64url");
  const claims = Buffer.from(JSON.stringify({...payload, iat: 1700000000, exp: 1700000300})).toString("base64url");
  const input = header + "." + claims;
  return input + "." + crypto.createHmac("sha256", secret).update(input).digest("base64url");
}

function decode(token) {
  const [header, payload, signature] = token.split(".");
  assert.equal(signature, crypto.createHmac("sha256", SECRET).update(header + "." + payload).digest("base64url"));
  const {iat, exp, ...fields} = JSON.parse(Buffer.from(payload, "base64url").toString());
  assert.equal(exp - iat, 300);
  return fields;
}

function fixture({enabled = true, signingError = false, senderLength = 4} = {}) {
  let sends = 0;
  let checks = 0;
  let hookLoads = 0;
  const utils = {
    canIncludeOutboxAuthorization() { return enabled; },
    fillJwtForRequest(ctx, data, secret, inBody) {
      if (signingError) throw new Error("Signing failed");
      const payload = structuredClone(data);
      return encode(inBody ? payload : {payload}, secret);
    },
  };
  // Retain the pinned sender's body-before-trim order so the correction must run before signing.
  async function sendServerRequest(ctx, uri, data, checkLength) {
    let header;
    let token;
    if (enabled) {
      token = utils.fillJwtForRequest(ctx, data, SECRET, true);
      header = utils.fillJwtForRequest(ctx, data, SECRET, false);
      if (checkLength && !checkLength(header, data)) {
        header = utils.fillJwtForRequest(ctx, data, SECRET, false);
      }
    }
    sends++;
    return {body: structuredClone(data), token, header, uri};
  }
  Object.defineProperty(sendServerRequest, "length", {value: senderLength});
  const docs = {sendServerRequest};
  const modules = {
    [DOCS]: docs,
    [COMMON + "utils.js"]: utils,
    [COMMON + "tenantManager.js"]: {async getTenantSecret() { return SECRET; }},
    [COMMON + "commondefines.js"]: {c_oAscSecretType: {Outbox: 2}},
  };
  const moduleLoader = {
    _load(name) {
      hookLoads++;
      if (name in modules) return modules[name];
      throw new Error("Unexpected module");
    },
    _resolveFilename(name) { return name; },
  };
  const originalLoad = moduleLoader._load;
  function withModuleLoader(action) {
    const realLoad = Module._load;
    const realResolve = Module._resolveFilename;
    Module._load = moduleLoader._load;
    Module._resolveFilename = moduleLoader._resolveFilename;
    try {
      return action();
    } finally {
      Module._load = realLoad;
      Module._resolveFilename = realResolve;
    }
  }
  let hook;
  const assertInstalled = withModuleLoader(() => {
    const check = install();
    hook = Module._load;
    return check;
  });
  function load() {
    withModuleLoader(() => {
      Module._load = hook;
      Module._load(DOCS, {}, false);
      assertInstalled();
      assert.equal(Module._load, originalLoad);
    });
  }
  function checkLength(authorization, data) {
    checks++;
    if (authorization.length < 7168) return true;
    delete data.changesurl;
    data.history = {};
    return false;
  }
  return {
    load, assertInstalled, checkLength, docs, utils,
    counts() { return {sends, checks, hookLoads}; },
    async send(fields, check = checkLength) {
      return docs.sendServerRequest({}, "https://odoo.example/callback/private", structuredClone(fields), check);
    },
  };
}

function assertMatching(result) {
  assert.deepEqual(decode(result.token), result.body);
  assert.deepEqual(decode(result.header), {payload: result.body});
}

function fieldsAtHeaderLength(length) {
  for (let size = 4900; size < 5500; size++) {
    const fields = {...FIELDS, history: {changes: [{user: {id: "7", name: "x".repeat(size)}}]}};
    if (encode({payload: fields}, SECRET).length === length) return fields;
  }
  throw new Error("Boundary fixture could not be constructed");
}

test("large native history is finalized before both tokens are signed", async () => {
  const f = fixture();
  f.load();
  const fields = {...FIELDS, history: {changes: new Array(2000).fill(FIELDS.history.changes[0])}};
  const result = await f.send(fields);
  assertMatching(result);
  const expected = {...FIELDS, history: {}};
  delete expected.changesurl;
  assert.deepEqual(result.body, expected);
  assert.ok(result.header.length < 7168);
  assert.deepEqual(f.counts(), {sends: 1, checks: 1, hookLoads: 4});
});

for (const length of [7167, 7168]) {
  test("the pinned " + length + " byte authorization boundary is preserved", async () => {
    const f = fixture();
    f.load();
    const fields = fieldsAtHeaderLength(length);
    const result = await f.send(fields);
    assertMatching(result);
    if (length < 7168) assert.deepEqual(result.body, fields);
    else {
      assert.deepEqual(result.body.history, {});
      assert.equal(result.body.changesurl, undefined);
    }
    assert.equal(f.counts().checks, 1);
  });
}

test("ordinary callbacks and callbacks with no trimming keep every field", async () => {
  const f = fixture();
  f.load();
  for (const check of [f.checkLength, undefined]) {
    const result = await f.docs.sendServerRequest({}, "https://odoo.example/callback/private", structuredClone(FIELDS), check);
    assertMatching(result);
    assert.deepEqual(result.body, FIELDS);
  }
  assert.equal(f.counts().checks, 1);
});

test("authentication-disabled or excluded requests retain upstream behavior", async () => {
  const f = fixture({enabled: false});
  f.load();
  const result = await f.send(FIELDS);
  assert.deepEqual(result.body, FIELDS);
  assert.equal(result.token, undefined);
  assert.equal(result.header, undefined);
  assert.equal(f.counts().checks, 0);
});

test("signing and malformed trimming failures prevent transport", async () => {
  const signing = fixture({signingError: true});
  signing.load();
  await assert.rejects(signing.send(FIELDS), /Signing failed/);
  assert.equal(signing.counts().sends, 0);
  const malformed = fixture();
  malformed.load();
  await assert.rejects(malformed.send(FIELDS, {}), /checkLength is not a function/);
  assert.equal(malformed.counts().sends, 0);
});

test("an absent or changed sender contract fails startup", () => {
  const unloaded = fixture();
  assert.throws(unloaded.assertInstalled, /was not installed/);
  const changed = fixture({senderLength: 3});
  assert.throws(changed.load, /Unexpected ONLYOFFICE callback signing contract/);
});
