"use strict";

const http = require("node:http");
const https = require("node:https");
const {serverTLS} = require("./fixture_tls.cjs");

function isFixtureHost(value) {
  const loopback = /^(?:localhost|127\.0\.0\.1):([1-9]\d{0,4})$/.exec(value ?? "");
  return value === "garage-tls:3900" || Boolean(loopback && Number(loopback[1]) <= 65535);
}

function gateway(tls, socketPath = "/run/garage-s3/s3.sock") {
  return https.createServer(tls, (req, res) => {
    if (!req.url.startsWith("/") || req.url.startsWith("//") ||
        !isFixtureHost(req.headers.host)) {
      res.writeHead(400); res.end(); return;
    }
    // No plaintext network hop: Garage accepts this HTTP stream only through its shared Unix socket.
    const upstream = http.request({socketPath, method: req.method, path: req.url, headers: req.headers}, answer => {
      res.writeHead(answer.statusCode, answer.headers);
      answer.pipe(res);
    });
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
module.exports = {gateway, isFixtureHost};
