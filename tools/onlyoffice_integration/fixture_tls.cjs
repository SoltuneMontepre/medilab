"use strict";

const fs = require("node:fs");
const path = require("node:path");

function serverTLS() {
  const directory = process.env.ONLYOFFICE_FIXTURE_TLS_DIR ?? "/run/fixture-tls";
  return {
    key: fs.readFileSync(path.join(directory, "tls.key")),
    cert: fs.readFileSync(path.join(directory, "tls.crt")),
    ca: fs.readFileSync("/run/fixture-ca/ca.crt"),
    minVersion: "TLSv1.2",
  };
}

module.exports = {serverTLS};
