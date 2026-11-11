"use strict";

const assert = require("node:assert/strict");
const https = require("node:https");
const {fixtureTLS} = require("./test_tls.cjs");
const {once} = require("node:events");
const test = require("node:test");
const {proxy, requestPath, requestURL, requestHeaders, responseHeaders, websocketHeaders} = require("./loopback_proxy.cjs");

const KEY = "dGhlIHNhbXBsZSBub25jZQ==";
const upgrade = {host: "localhost:8081", connection: "keep-alive, Upgrade", upgrade: "websocket",
  "sec-websocket-key": KEY, "sec-websocket-version": "13"};

test("fixed upstream authority and presigned query survive without normalization", () => {
  const path = "/laboratory-files-fixture/report%20one.docx?signature=A%2FB%2B&host=other.example";
  const url = requestURL(path, 3900);
  assert.equal(url.origin, "https://garage-tls:3900");
  assert.equal(url.pathname + url.search, path);
  assert.equal(requestURL("/web-apps/file?url=https%3A%2F%2Fother.example", 8081).origin, "https://documentserver");
  assert.equal(requestPath("/laboratory-files/a%25b", 3900), "/laboratory-files/a%25b");
  assert.throws(() => proxy(80), /Unknown fixture proxy/);
});

test("authority confusion, repeated encoding and command routes are refused", () => {
  for (const path of ["https://other.example/file", "//other.example/file", String.raw`/\other.example/file`,
    "/a\r\nHost: other", "", "/a#fragment", "/../admin", "/%2e%2e/admin", "/%252e%252e/admin",
    "/a%252fb", "/a%255cb", "/a%250db", "/a%00b", "/a%FFb", "/bad%xy", "/command", "/coauthoring/CommandService.ashx",
    "/%2563ommand"]) {
    assert.throws(() => requestURL(path, 8081), path);
  }
  for (const path of ["/other-bucket/key", "/laboratory-files", "/laboratory-files/../../metadata"]) {
    assert.throws(() => requestURL(path, 3900), path);
  }
});

test("redirects are reconstructed from the approved origin and safe path", () => {
  for (const location of ["/cache/file", "https://localhost:8081/cache/file"]) {
    assert.equal(responseHeaders({location}, 8081).location, "https://localhost:8081/cache/file");
  }
  for (const location of ["https://other.example", "//other.example", "http://user@localhost:8081/file",
    "/cache/file#fragment", "/%252e%252e/admin", "https://localhost:8081/%2e%2e/admin", "/command"]) {
    assert.throws(() => responseHeaders({location}, 8081), location);
  }
});

test("only approved headers cross trust boundaries", () => {
  assert.equal(requestHeaders({host: "localhost:8081", cookie: "session=fixture"}, 8081).cookie, "session=fixture");
  assert.throws(() => requestHeaders({host: "other.example"}, 8081));
  const storage = requestHeaders({host: "localhost:3900", authorization: "private", cookie: "session=private"}, 3900);
  assert.equal(storage.authorization, undefined);
  assert.equal(storage.cookie, undefined);
  const headers = JSON.parse('{"content-type":"application/json","__proto__":{"polluted":true},"constructor":"unsafe"}');
  const result = responseHeaders(headers, 8081);
  assert.equal(Object.getPrototypeOf(result), null);
  assert.deepEqual(Object.keys(result), ["content-type"]);
  assert.equal({}.polluted, undefined);
  assert.throws(() => responseHeaders({"content-type":"text/plain\r\nLocation: https://other.example"}, 8081));
});

test("upgrades require an RFC WebSocket handshake and cannot carry HTTP bodies", () => {
  assert.equal(websocketHeaders({method: "GET", headers: upgrade}, 8081).upgrade, "websocket");
  for (const changes of [{upgrade: "other"}, {connection: "keep-alive"}, {"sec-websocket-key": "invalid"},
    {"sec-websocket-version": "12"}, {"content-length": "0"}, {"transfer-encoding": "chunked"}]) {
    assert.throws(() => websocketHeaders({method: "GET", headers: {...upgrade, ...changes}}, 8081));
  }
  assert.throws(() => websocketHeaders({method: "POST", headers: upgrade}, 8081));
  assert.throws(() => websocketHeaders({method: "GET", headers: {...upgrade, host: "localhost:3900"}}, 3900));
});

async function fixture(t, handler, upstreamName) {
  const tls = fixtureTLS(t);
  const peerTLS = fixtureTLS(t, "DNS:documentserver");
  tls.ca = peerTLS.cert;
  const original = https.request;
  const upstream = https.createServer(peerTLS, handler).listen(0, "127.0.0.1");
  await once(upstream, "listening");
  const calls = [];
  t.mock.method(https, "request", (url, options, callback) => {
    assert.ok(url instanceof URL);
    assert.equal(url.origin, "https://documentserver");
    assert.equal(options.servername, "documentserver");
    calls.push(url.pathname + url.search);
    return original({hostname: "127.0.0.1", port: upstream.address().port,
      path: url.pathname + url.search, ...options, ...(upstreamName ? {servername: upstreamName} : {})}, callback);
  });
  const server = proxy(8081, tls, 0);
  await once(server, "listening");
  t.after(() => { server.closeAllConnections(); server.close(); upstream.closeAllConnections(); upstream.close(); });
  return {upstream, server, calls, original, tls};
}

function fetch(f, path, method = "GET") {
  return new Promise((resolve, reject) => {
    const req = f.original({hostname: "127.0.0.1", port: f.server.address().port, path, method, ca: f.tls.cert,
      headers: {host: "localhost:8081"}}, res => {
      const body = [];
      res.on("data", chunk => body.push(chunk));
      res.on("end", () => resolve({status: res.statusCode, headers: res.headers, body: Buffer.concat(body).toString()}));
    });
    req.on("error", reject);
    req.end();
  });
}

test("real HTTPS forwarding preserves bytes and rejects unsafe redirects before headers", {timeout: 5000}, async t => {
  const f = await fixture(t, (req, res) => {
    if (req.url === "/redirect") res.writeHead(302, {location: "/cache/file"});
    else if (req.url === "/foreign") res.writeHead(302, {location: "https://other.example/private"});
    else res.writeHead(200, {"content-type": "application/octet-stream"});
    res.end("fixture bytes");
  });
  assert.equal((await fetch(f, "/cache/file?token=A%2FB")).body, "fixture bytes");
  assert.equal((await fetch(f, "/redirect")).headers.location, "https://localhost:8081/cache/file");
  assert.equal((await fetch(f, "/foreign")).status, 502);
  const count = f.calls.length;
  const refused = await Promise.all(["//other.example/path", "/%252e%252e/admin",
    "https://localhost:8081/%2e%2e/admin", "/command"].map(path => fetch(f, path)));
  for (const answer of refused) assert.equal(answer.status, 400);
  assert.equal((await fetch(f, "/cache/file", "DELETE")).status, 400);
  assert.equal(f.calls.length, count);
});

test("real WebSocket tunnel starts only after the fixed upstream authenticates its handshake", {timeout: 5000}, async t => {
  const f = await fixture(t, (_req, res) => { res.writeHead(404); res.end(); });
  f.upstream.on("upgrade", (req, socket) => {
    const accept = req.url === "/invalid" ? "invalid" : "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=";
    socket.write(`HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Accept: ${accept}\r\n\r\n`);
    socket.on("data", bytes => socket.write(bytes));
    socket.on("error", () => {});
    t.after(() => socket.destroy());
  });
  const request = path => f.original({hostname: "127.0.0.1", port: f.server.address().port, path, ca: f.tls.cert, headers: upgrade});
  const req = request("/coauthoring");
  const connected = once(req, "upgrade");
  req.end();
  const [response, socket] = await connected;
  t.after(() => socket.destroy());
  assert.equal(response.statusCode, 101);
  socket.write("exact fixture bytes");
  assert.equal((await once(socket, "data"))[0].toString(), "exact fixture bytes");
  const bad = request("/invalid");
  bad.on("upgrade", () => assert.fail("Invalid handshake was forwarded"));
  const error = once(bad, "error");
  bad.end();
  assert.equal((await error)[0].code, "ECONNRESET");
});

for (const refusal of ["untrusted CA", "wrong server identity"]) {
  test(`TLS forwarding refuses ${refusal} before sending application bytes`, {timeout: 5000}, async t => {
    let requests = 0;
    const f = await fixture(t, (_req, res) => { requests++; res.end("must not arrive"); },
      refusal === "wrong server identity" ? "foreign.example" : undefined);
    if (refusal === "untrusted CA") f.tls.ca = fixtureTLS(t).cert;
    assert.equal((await fetch(f, "/cache/file")).status, 502);
    assert.equal(requests, 0);
  });
}
