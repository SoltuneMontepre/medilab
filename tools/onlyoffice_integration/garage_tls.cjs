"use strict";

const http = require("node:http");
const https = require("node:https");
const {serverTLS} = require("./fixture_tls.cjs");
const {selectHeaders, validateSegment} = require("./loopback_proxy.cjs");

const REQUEST_HEADERS = ["host", "authorization", "accept", "accept-encoding", "cache-control",
  "content-type", "content-length", "content-md5", "content-encoding", "content-disposition",
  "trailer", "x-amz-decoded-content-length", "x-amz-trailer", "x-amz-checksum-mode",
  "expect", "range", "if-match", "if-none-match", "if-modified-since", "if-unmodified-since",
  "x-amz-content-sha256", "x-amz-date", "x-amz-security-token", "x-amz-sdk-checksum-algorithm",
  "x-amz-checksum-crc32", "x-amz-checksum-crc32c", "x-amz-checksum-sha1", "x-amz-checksum-sha256",
  "x-amz-copy-source", "x-amz-copy-source-if-match", "x-amz-metadata-directive",
  "amz-sdk-invocation-id", "amz-sdk-request", "user-agent"];
const RESPONSE_HEADERS = ["accept-ranges", "content-type", "content-length", "content-encoding",
  "content-range", "content-disposition", "date", "etag", "last-modified", "x-amz-id-2",
  "x-amz-request-id", "x-amz-version-id", "x-amz-delete-marker", "x-amz-bucket-region",
  "x-amz-checksum-crc32", "x-amz-checksum-crc32c", "x-amz-checksum-sha1", "x-amz-checksum-sha256"];
const METHODS = new Set(["GET", "HEAD", "PUT", "POST", "DELETE", "OPTIONS"]);

function isFixtureHost(value) {
  const loopback = /^(?:localhost|127\.0\.0\.1):([1-9]\d{0,4})$/.exec(value ?? "");
  return value === "garage-tls:3900" || Boolean(loopback && Number(loopback[1]) <= 65535);
}

function gatewayPath(raw) {
  if (typeof raw !== "string" || raw.length > 65536 || !raw.startsWith("/") ||
      raw.startsWith("//") || /[\x00-\x20\x7f\\#]/u.test(raw)) {
    throw new Error("Invalid fixture request target");
  }
  const pathname = raw.split("?", 1)[0];
  if (!/^\/(?:$|laboratory-files(?:-[a-z0-9-]{1,63})?(?:\/|$))/u.test(pathname)) {
    throw new Error("Invalid fixture bucket");
  }
  for (const segment of pathname.split("/")) validateSegment(segment);
  return raw;
}

function forwardResponse(answer, res) {
  try {
    if (answer.statusCode >= 300 && answer.statusCode < 400 || answer.headers.location !== undefined) {
      throw new Error("Storage redirects are refused");
    }
    res.writeHead(answer.statusCode, selectHeaders(answer.headers, RESPONSE_HEADERS));
    answer.pipe(res);
  } catch {
    answer.destroy();
    res.writeHead(502);
    res.end();
  }
}

function gateway(tls, socketPath = "/run/garage-s3/s3.sock") {
  return https.createServer(tls, (req, res) => {
    let requestPath;
    let headers;
    try {
      if (!METHODS.has(req.method) || !isFixtureHost(req.headers.host)) {
        throw new Error("Invalid fixture request");
      }
      requestPath = gatewayPath(req.url);
      headers = selectHeaders(req.headers, REQUEST_HEADERS);
    } catch {
      res.writeHead(400); res.end(); return;
    }
    // Garage accepts this stream only through a fixed local Unix socket; request input cannot select a peer.
    const upstream = http.request({socketPath, method: req.method, path: requestPath, headers},
      answer => forwardResponse(answer, res));
    upstream.on("error", () => {
      if (!res.headersSent) res.writeHead(502);
      res.end();
    });
    upstream.setTimeout(30000, () => upstream.destroy());
    req.on("aborted", () => upstream.destroy());
    req.pipe(upstream);
  });
}

if (require.main === module) {
  if (process.env.MEDILAB_ONLYOFFICE_STORAGE_FIXTURE !== "isolated-owned") {
    throw new Error("Enable only in an explicitly owned isolated fixture");
  }
  gateway(serverTLS()).listen(3900, "0.0.0.0");
}
module.exports = {gateway, isFixtureHost, gatewayPath};
