"use strict";

const crypto = require("node:crypto");
const http = require("node:http");
const https = require("node:https");
const {serverTLS} = require("./fixture_tls.cjs");

const TARGETS = new Map([
  [8081, {upstream: "https://documentserver", origin: "https://localhost:8081"}],
  [3900, {upstream: "https://garage-tls:3900", origin: "https://localhost:3900"}],
]);
const REQUEST_HEADERS = ["host", "accept", "accept-encoding", "accept-language", "authorization", "cache-control",
  "content-length", "content-type", "cookie", "if-modified-since", "if-none-match", "origin", "range", "referer",
  "sec-websocket-key", "sec-websocket-version", "sec-websocket-extensions", "sec-websocket-protocol", "user-agent"];
const RESPONSE_HEADERS = ["accept-ranges", "access-control-allow-credentials", "access-control-allow-origin",
  "cache-control", "content-disposition", "content-encoding", "content-length", "content-range", "content-security-policy",
  "content-type", "date", "etag", "expires", "last-modified", "set-cookie", "vary", "x-content-type-options", "x-frame-options"];
const UPGRADE_HEADERS = ["sec-websocket-accept", "sec-websocket-protocol", "sec-websocket-extensions"];

function target(port) {
  const value = TARGETS.get(port);
  if (!value) throw new Error("Unknown fixture proxy");
  return value;
}

function validateSegment(segment) {
  let decoded = segment;
  for (let depth = 0; depth < 8; depth++) {
    if (decoded === "." || decoded === ".." || /[\x00-\x1f\x7f/\\]/u.test(decoded)) {
      throw new Error("Invalid fixture path segment");
    }
    if (!decoded.includes("%")) return decoded;
    if (/%(?![0-9a-f]{2})/iu.test(decoded)) {
      if (depth === 0) throw new Error("Invalid path encoding");
      return decoded;
    }
    decoded = decodeURIComponent(decoded);
  }
  throw new Error("Excessively encoded path");
}

function requestPath(raw, port) {
  target(port);
  if (typeof raw !== "string" || raw.length > 65536 || !raw.startsWith("/") || raw.startsWith("//") ||
      /[\x00-\x20\x7f\\#]/u.test(raw)) throw new Error("Invalid loopback request target");
  const pathname = raw.split("?", 1)[0];
  for (const segment of pathname.split("/")) {
    if (/^(command|commandservice\.ashx)$/iu.test(validateSegment(segment))) {
      throw new Error("Internal command route refused");
    }
  }
  if (port === 3900 && !/^\/laboratory-files(?:-[a-z0-9-]{1,63})?\//u.test(pathname)) {
    throw new Error("Invalid fixture bucket");
  }
  return raw;
}

function requestURL(raw, port) {
  const safe = requestPath(raw, port);
  const query = safe.indexOf("?");
  const pathname = query === -1 ? safe : safe.slice(0, query);
  const search = query === -1 ? "" : safe.slice(query);
  // Assign only path/query on a URL whose authority comes exclusively from the fixed fixture map.
  const url = new URL(target(port).upstream);
  url.pathname = pathname;
  url.search = search;
  if (url.pathname !== pathname || url.search !== search) throw new Error("Noncanonical request target");
  return url;
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
    const origin = target(port).origin;
    const location = headers.location;
    if (typeof location !== "string") throw new Error("Refused upstream redirect");
    const path = location.startsWith(origin + "/") ? location.slice(origin.length) : location;
    const validated = requestURL(path, port);
    const safe = new URL(origin);
    safe.pathname = validated.pathname;
    safe.search = validated.search;
    result.location = safe.href;
  }
  return result;
}

function requestHeaders(headers, port) {
  target(port);
  if (![`localhost:${port}`, `127.0.0.1:${port}`].includes(headers.host)) throw new Error("Invalid fixture host");
  const allowed = port === 3900 ? REQUEST_HEADERS.filter(name => !["authorization", "cookie"].includes(name)) : REQUEST_HEADERS;
  return selectHeaders(headers, allowed);
}

function websocketHeaders(req, port) {
  const headers = requestHeaders(req.headers, port);
  if (port !== 8081 || req.method !== "GET" || req.headers.upgrade?.toLowerCase() !== "websocket" ||
      !req.headers.connection?.toLowerCase().split(",").map(value => value.trim()).includes("upgrade") ||
      req.headers["sec-websocket-version"] !== "13" || !/^[a-z0-9+/]{22}==$/iu.test(req.headers["sec-websocket-key"] ?? "") ||
      req.headers["content-length"] !== undefined || req.headers["transfer-encoding"] !== undefined) {
    throw new Error("Invalid WebSocket upgrade");
  }
  return {...headers, connection: "Upgrade", upgrade: "websocket"};
}

function proxy(port, tls, listenPort = port) {
  target(port);
  tls ??= serverTLS();
  const server = https.createServer(tls, (req, res) => {
    let url;
    let headers;
    try {
      if (!["GET", "HEAD", "POST", "OPTIONS"].includes(req.method) || (port === 3900 && req.method === "POST")) {
        throw new Error("Unsupported fixture method");
      }
      url = requestURL(req.url, port);
      headers = requestHeaders(req.headers, port);
    } catch {
      res.writeHead(400); res.end(); return;
    }
    const upstream = https.request(url, {method: req.method, headers, ca: tls.ca, servername: url.hostname}, answer => {
      try {
        res.writeHead(answer.statusCode, responseHeaders(answer.headers, port));
      } catch {
        answer.destroy(); res.writeHead(502); res.end(); return;
      }
      answer.pipe(res);
    });
    upstream.on("error", () => {
      if (!res.headersSent) res.writeHead(502);
      res.end();
    });
    req.on("aborted", () => upstream.destroy());
    req.pipe(upstream);
  });
  server.on("upgrade", (req, socket, head) => {
    let url;
    let headers;
    try {
      url = requestURL(req.url, port);
      headers = websocketHeaders(req, port);
    } catch {
      socket.destroy(); return;
    }
    const upstream = https.request(url, {method: "GET", headers, ca: tls.ca, servername: url.hostname});
    upstream.on("upgrade", (answer, tunnel, upstreamHead) => {
      // RFC 6455 4.2.2/10.8: public nonce framing only; this is not a credential or integrity hash.
      const expected = crypto.createHash("sha1").update(req.headers["sec-websocket-key"] +
        "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest("base64");
      try {
        if (answer.statusCode !== 101 || answer.headers["sec-websocket-accept"] !== expected) {
          throw new Error("Invalid upstream handshake");
        }
        tunnel.setTimeout(0);
        const fields = selectHeaders(answer.headers, UPGRADE_HEADERS);
        socket.write("HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n");
        for (const [name, value] of Object.entries(fields)) socket.write(`${name}: ${value}\r\n`);
        socket.write("\r\n");
        if (upstreamHead.length) socket.write(upstreamHead);
        if (head.length) tunnel.write(head);
        tunnel.pipe(socket).pipe(tunnel);
      } catch {
        tunnel.destroy(); socket.destroy();
      }
      tunnel.on("error", () => socket.destroy());
      socket.on("error", () => tunnel.destroy());
      socket.on("close", () => tunnel.destroy());
    });
    upstream.on("response", response => { response.destroy(); socket.destroy(); });
    upstream.on("error", () => socket.destroy());
    upstream.setTimeout(10000, () => { upstream.destroy(); socket.destroy(); });
    upstream.end();
  });
  return server.listen(listenPort, "127.0.0.1");
}

module.exports = {proxy, requestPath, requestURL, requestHeaders, responseHeaders, websocketHeaders, validateSegment, selectHeaders};
