"use strict";

const http = require("node:http");
const net = require("node:net");

const TARGETS = new Map([
  [8081, {hostname: "documentserver", port: 80}],
  [3900, {hostname: "garage", port: 3900}],
]);
const REQUEST_HEADERS = ["host", "accept", "accept-encoding", "accept-language", "authorization", "cache-control",
  "content-length", "content-type", "cookie", "if-modified-since", "if-none-match", "origin", "range", "referer",
  "sec-websocket-key", "sec-websocket-version", "sec-websocket-extensions", "sec-websocket-protocol", "user-agent"];
const RESPONSE_HEADERS = ["accept-ranges", "access-control-allow-credentials", "access-control-allow-origin",
  "cache-control", "content-disposition", "content-encoding", "content-length", "content-range", "content-security-policy",
  "content-type", "date", "etag", "expires", "last-modified", "set-cookie", "vary", "x-content-type-options", "x-frame-options"];

function requestPath(raw, port) {
  if (typeof raw !== "string" || !raw.startsWith("/") || raw.startsWith("//") || /[\x00-\x20\x7f\\]/u.test(raw)) {
    throw new Error("Invalid loopback request target");
  }
  const origin = `http://localhost:${port}`;
  const url = new URL(raw, origin);
  if (url.origin !== origin || url.username || url.password || url.hash) throw new Error("Invalid loopback origin");
  return url.pathname + url.search;
}

function selectHeaders(headers, allowed) {
  const result = Object.create(null);
  for (const name of allowed) {
    const value = headers[name];
    if (value === undefined) continue;
    http.validateHeaderValue(name, value);
    result[name] = value;
  }
  return result;
}

function responseHeaders(headers, port) {
  const result = selectHeaders(headers, RESPONSE_HEADERS);
  if (headers.location !== undefined) {
    const origin = `http://localhost:${port}`;
    const location = new URL(headers.location, origin);
    if (location.origin !== origin || location.username || location.password) throw new Error("Refused upstream redirect");
    result.location = requestPath(location.pathname + location.search, port);
  }
  return result;
}

function requestHeaders(headers, port) {
  if (![ `localhost:${port}`, `127.0.0.1:${port}` ].includes(headers.host)) throw new Error("Invalid fixture host");
  return selectHeaders(headers, REQUEST_HEADERS);
}

function proxy(port) {
  const target = TARGETS.get(port);
  if (!target) throw new Error("Unknown fixture proxy");
  const server = http.createServer((req, res) => {
    let path;
    let headers;
    try {
      path = requestPath(req.url, port);
      headers = requestHeaders(req.headers, port);
    } catch {
      res.writeHead(400); res.end(); return;
    }
    const upstream = http.request({hostname: target.hostname, port: target.port, path, method: req.method, headers}, answer => {
      try {
        res.writeHead(answer.statusCode, responseHeaders(answer.headers, port));
      } catch {
        answer.destroy(); res.writeHead(502); res.end(); return;
      }
      answer.pipe(res);
    });
    upstream.on("error", () => {
      if (!res.headersSent) {
        res.writeHead(502);
      }
      res.end();
    });
    req.pipe(upstream);
  });
  server.on("upgrade", (req, socket, head) => {
    let path;
    let headers;
    try {
      if (req.method !== "GET") throw new Error("Invalid upgrade method");
      path = requestPath(req.url, port);
      headers = requestHeaders(req.headers, port);
    } catch {
      socket.destroy(); return;
    }
    const upstream = net.connect(target.port, target.hostname, () => {
      upstream.write(`GET ${path} HTTP/1.1\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n`);
      for (const [name, value] of Object.entries(headers)) upstream.write(`${name}: ${value}\r\n`);
      upstream.write("\r\n"); upstream.write(head); socket.pipe(upstream).pipe(socket);
    });
    upstream.on("error", () => socket.destroy());
    socket.on("error", () => upstream.destroy());
  });
  return server.listen(port, "127.0.0.1");
}

module.exports = {proxy, requestPath, requestHeaders, responseHeaders};
