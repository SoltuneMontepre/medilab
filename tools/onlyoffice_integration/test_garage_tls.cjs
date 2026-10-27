"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const https = require("node:https");
const os = require("node:os");
const path = require("node:path");
const {once} = require("node:events");
const test = require("node:test");
const {gateway, isFixtureHost} = require("./garage_tls.cjs");
const {fixtureTLS} = require("./test_tls.cjs");

test("signed loopback proxy ports remain valid without accepting foreign authorities", () => {
  for (const host of ["garage-tls:3900", "localhost:3900", "127.0.0.1:54321"]) assert.equal(isFixtureHost(host), true);
  for (const host of [undefined, "other.example:3900", "localhost:0", "127.0.0.1:65536", "localhost:3900@other"])
    assert.equal(isFixtureHost(host), false);
});

test("verified TLS forwards exact signed Host, query and body through a Unix socket", {timeout: 5000}, async t => {
  const tls = fixtureTLS(t);
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "medilab-garage-ipc-"));
  t.after(() => fs.rmSync(directory, {recursive: true, force: true}));
  const socketPath = path.join(directory, "s3.sock");
  const calls = [];
  const upstream = http.createServer((req, res) => {
    const bytes = [];
    req.on("data", chunk => bytes.push(chunk));
    req.on("end", () => {
      calls.push({host: req.headers.host, path: req.url, body: Buffer.concat(bytes).toString()});
      res.end("immutable fixture bytes");
    });
  }).listen(socketPath);
  await once(upstream, "listening");
  const server = gateway(tls, socketPath).listen(0, "127.0.0.1");
  await once(server, "listening");
  t.after(() => { server.closeAllConnections(); server.close(); upstream.closeAllConnections(); upstream.close(); });
  const response = await new Promise((resolve, reject) => {
    const req = https.request({hostname: "127.0.0.1", port: server.address().port, ca: tls.ca, method: "PUT",
      path: "/laboratory-files/report%20one.docx?signature=A%2FB%2B", headers: {host: "localhost:3900"}}, res => {
      const bytes = [];
      res.on("data", chunk => bytes.push(chunk));
      res.on("end", () => resolve(Buffer.concat(bytes).toString()));
    });
    req.on("error", reject);
    req.end("signed request bytes");
  });
  assert.equal(response, "immutable fixture bytes");
  assert.deepEqual(calls, [{host: "localhost:3900", path: "/laboratory-files/report%20one.docx?signature=A%2FB%2B",
    body: "signed request bytes"}]);
  assert.equal(upstream.address(), socketPath);
});
