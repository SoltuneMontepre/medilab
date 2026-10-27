"use strict";

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const {execFileSync} = require("node:child_process");

function fixtureTLS(t, names = "DNS:localhost,IP:127.0.0.1") {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "medilab-fixture-tls-"));
  fs.chmodSync(directory, 0o700);
  t.after(() => fs.rmSync(directory, {recursive: true, force: true}));
  const key = path.join(directory, "key.pem");
  const cert = path.join(directory, "cert.pem");
  execFileSync("openssl", ["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-sha256", "-days", "1",
    "-keyout", key, "-out", cert, "-subj", "/CN=MediLab disposable test",
    "-addext", "subjectAltName=" + names], {stdio: "ignore"});
  return {key: fs.readFileSync(key), cert: fs.readFileSync(cert), ca: fs.readFileSync(cert), minVersion: "TLSv1.2"};
}

module.exports = {fixtureTLS};
