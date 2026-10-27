"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const https = require("node:https");
const os = require("node:os");
const path = require("node:path");
const {once} = require("node:events");
const test = require("node:test");
const {gateway, isFixtureHost, gatewayPath} = require("./garage_tls.cjs");
const {fixtureTLS} = require("./test_tls.cjs");

test("signed loopback proxy ports remain valid without accepting foreign authorities", () => {
  for (const host of ["garage-tls:3900", "localhost:3900", "127.0.0.1:54321"]) assert.equal(isFixtureHost(host), true);
  for (const host of [undefined, "other.example:3900", "localhost:0", "127.0.0.1:65536", "localhost:3900@other"])
    assert.equal(isFixtureHost(host), false);
});

test("storage gateway accepts only owned origin-relative targets without changing signed bytes", () => {
  const signed = "/laboratory-files/report%20one.docx?signature=A%2FB%2B&next=https%3A%2F%2Fother.example";
  for (const target of ["/", "/laboratory-files", signed]) assert.equal(gatewayPath(target), target);
  for (const target of ["//other.example/path", "https://other.example/path", "/other-bucket/key",
    "/laboratory-files/%252e%252e/file", "/laboratory-files/x%2fy", "/laboratory-files/x\\y",
    "/laboratory-files/x\r\nHost:other", "/laboratory-files/x#fragment"])
    assert.throws(() => gatewayPath(target), /Invalid/);
});

async function fixture(t, handler) {
  const tls = fixtureTLS(t);
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "medilab-garage-ipc-"));
  t.after(() => fs.rmSync(directory, {recursive: true, force: true}));
  const socketPath = path.join(directory, "s3.sock");
  const upstream = http.createServer(handler).listen(socketPath);
  await once(upstream, "listening");
  const server = gateway(tls, socketPath).listen(0, "127.0.0.1");
  await once(server, "listening");
  t.after(() => { server.closeAllConnections(); server.close(); upstream.closeAllConnections(); upstream.close(); });
  return {
    socketPath,
    upstream,
    request(target, method = "GET", body = "") {
      return new Promise((resolve, reject) => {
        const req = https.request({hostname: "127.0.0.1", port: server.address().port, ca: tls.ca,
          method, path: target, headers: {host: "localhost:3900"}}, res => {
          const bytes = [];
          res.on("data", chunk => bytes.push(chunk));
          res.on("end", () => resolve({status: res.statusCode, headers: res.headers, body: Buffer.concat(bytes).toString()}));
        });
        req.on("error", reject);
        req.end(body);
      });
    },
  };
}

test("verified TLS forwards exact signed Host, query and body through a Unix socket", {timeout: 5000}, async t => {
  const calls = [];
  const client = await fixture(t, (req, res) => {
    const bytes = [];
    req.on("data", chunk => bytes.push(chunk));
    req.on("end", () => {
      calls.push({host: req.headers.host, path: req.url, body: Buffer.concat(bytes).toString()});
      res.end("immutable fixture bytes");
    });
  });
  const response = await client.request("/laboratory-files/report%20one.docx?signature=A%2FB%2B", "PUT", "signed request bytes");
  assert.equal(response.body, "immutable fixture bytes");
  assert.deepEqual(calls, [{host: "localhost:3900", path: "/laboratory-files/report%20one.docx?signature=A%2FB%2B",
    body: "signed request bytes"}]);
  assert.equal(client.upstream.address(), client.socketPath);
});

test("malicious targets never reach even the fixed Unix peer", {timeout: 5000}, async t => {
  let calls = 0;
  const client = await fixture(t, (_req, res) => { calls++; res.end(); });
  const results = await Promise.all(["//other.example/path", "https://other.example/path", "/other-bucket/key",
    "/laboratory-files/%252e%252e/file"].map(target => client.request(target)));
  assert.deepEqual(results.map(result => result.status), [400, 400, 400, 400]);
  assert.equal(calls, 0);
});

test("compromised storage cannot forward redirects or object-shaped header names", {timeout: 5000}, async t => {
  const client = await fixture(t, (req, res) => {
    if (req.url.endsWith("/redirect")) {
      res.writeHead(302, {location: "https://other.example/leak"}); res.end(); return;
    }
    res.setHeader("__proto__", "polluted");
    res.setHeader("constructor", "polluted");
    res.setHeader("set-cookie", "not-forwarded");
    res.setHeader("x-unreviewed", "not-forwarded");
    res.setHeader("etag", "owned-etag");
    res.setHeader("x-amz-request-id", "owned-request");
    res.end("immutable fixture bytes");
  });
  const redirected = await client.request("/laboratory-files/redirect");
  assert.equal(redirected.status, 502);
  assert.equal(redirected.headers.location, undefined);
  const response = await client.request("/laboratory-files/safe");
  assert.equal(response.status, 200);
  assert.equal(response.body, "immutable fixture bytes");
  for (const name of ["__proto__", "constructor", "set-cookie", "x-unreviewed"])
    assert.equal(Object.hasOwn(response.headers, name), false);
  assert.equal(response.headers.etag, "owned-etag");
  assert.equal(response.headers["x-amz-request-id"], "owned-request");
  assert.equal(Object.prototype.polluted, undefined);
});

test("fixture key generation ignores a caller-controlled executable PATH", t => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "medilab-fake-openssl-"));
  t.after(() => fs.rmSync(directory, {recursive: true, force: true}));
  fs.writeFileSync(path.join(directory, "openssl"), "#!/bin/sh\nexit 73\n", {mode: 0o700});
  const previousPath = process.env.PATH;
  try {
    process.env.PATH = directory;
    const tls = fixtureTLS(t);
    assert.ok(tls.cert.includes(Buffer.from("BEGIN CERTIFICATE")));
  } finally {
    if (previousPath === undefined) delete process.env.PATH;
    else process.env.PATH = previousPath;
  }
});
