'use strict';

// Use pkg's native fork entrypoint so policy is checked inside the actual worker.
const fs = require('fs');
const crypto = require('crypto');
const path = require('path');
const assert = require('assert/strict');
const CONTEXTS = {
  '/var/www/onlyoffice/documentserver/server/DocService/docservice': {
    name: 'docservice',
    entry: '/snapshot/server/DocService/sources/server.js',
    sha256: '556df4aab7b1a87123046a4459baee34e60f57deaf7bcd189bccd6f271bd8fcb',
  },
  '/var/www/onlyoffice/documentserver/server/FileConverter/converter': {
    name: 'converter',
    entry: '/snapshot/server/FileConverter/sources/convertermaster.js',
    sha256: 'ac76144203fd4e8fdee4cccac976697e87ec9b67b7bdf572e6ea1288524a8f80',
  },
};
const CONFIG_MODULE = '/snapshot/server/Common/node_modules/config';
const SETTINGS = '/opt/medilab/onlyoffice/settings.json';
const REPORT_DIRECTORY = '/run/onlyoffice-runtime';
const RUNTIME_CONFIG = '/var/www/onlyoffice/Data/runtime.json';
let stage = 'context';

function digest(filename) {
  const hash = crypto.createHash('sha256');
  const descriptor = fs.openSync(filename, 'r');
  const buffer = Buffer.alloc(65536);
  try {
    let size;
    while ((size = fs.readSync(descriptor, buffer, 0, buffer.length, null)) !== 0) {
      hash.update(buffer.subarray(0, size));
    }
  } finally {
    fs.closeSync(descriptor);
  }
  return hash.digest('hex');
}

function runtimeDigest() {
  try {
    return digest(RUNTIME_CONFIG);
  } catch (error) {
    if (error.code === 'ENOENT') return null;
    throw error;
  }
}

function checkPolicy(config, expected, prefix = '') {
  for (const [key, value] of Object.entries(expected)) {
    const name = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      checkPolicy(config, value, name);
    } else {
      assert.deepEqual(config.get(name), value);
    }
  }
}

function policy(config) {
  const get = name => config.get(`services.CoAuthoring.${name}`);
  const outbox = {};
  for (const name of ['header', 'prefix', 'inBody', 'algorithm', 'expires', 'urlExclusionRegex']) {
    outbox[name] = get(`token.outbox.${name}`);
  }
  return {
    callbackRequestTimeout: get('server.callbackRequestTimeout'),
    cache_files: get('expire.files'),
    outbox,
    tlsVerification: get('requestDefaults.rejectUnauthorized'),
    callbackBackoffOptions: get('callbackBackoffOptions'),
    autoAssembly: get('autoAssembly.enable'),
    runtimeConfigFile: path.resolve(config.get('runtimeConfig.filePath')),
  };
}

function main() {
  const context = CONTEXTS[process.execPath];
  assert(context && process.pkg && process.pkg.defaultEntrypoint === context.entry);
  assert.equal(process.pkg.entrypoint, '/opt/medilab/onlyoffice/worker-bootstrap.cjs');
  assert.equal(process.argv[1], process.pkg.entrypoint);
  assert.equal(process.env.NODE_ENV, 'production-linux');
  assert.equal(process.env.NODE_CONFIG_DIR, '/etc/onlyoffice/documentserver');
  stage = 'binary';
  assert.equal(digest(process.execPath), context.sha256);
  stage = 'settings';
  const settings = fs.readFileSync(SETTINGS, 'utf8');
  const expected = JSON.parse(settings);
  assert.deepEqual(JSON.parse(process.env.NODE_CONFIG), expected);
  assert.equal(path.resolve(require(CONFIG_MODULE).get('runtimeConfig.filePath')), RUNTIME_CONFIG);
  const runtimeHash = runtimeDigest();
  stage = 'sender';
  let assertSender = () => {};
  if (context.name === 'docservice') {
    assertSender = require('./callback-signing.cjs').install();
  }
  stage = 'entry';
  require(context.entry);
  assertSender();
  // The original entrypoint has now applied ONLYOFFICE's runtime configuration merge.
  const config = require(CONFIG_MODULE);
  stage = 'effective-policy';
  checkPolicy(config, expected);
  stage = 'runtime-override';
  assert.equal(path.resolve(config.get('runtimeConfig.filePath')), RUNTIME_CONFIG);
  assert.equal(runtimeDigest(), runtimeHash);
  stage = 'attestation';
  const stat = fs.readFileSync('/proc/self/stat', 'utf8');
  const report = {
    worker: context.name,
    pid: process.pid,
    startTicks: stat.slice(stat.lastIndexOf(')') + 2).trim().split(/\s+/)[19],
    binarySha256: context.sha256,
    settingsSha256: crypto.createHash('sha256').update(settings).digest('hex'),
    runtimeConfigSha256: runtimeHash,
    policy: policy(config),
  };
  const target = path.join(REPORT_DIRECTORY, `${context.name}-${process.pid}.json`);
  const temporary = `${target}.${process.pid}`;
  fs.writeFileSync(temporary, `${JSON.stringify(report)}\n`, {mode: 0o600, flag: 'wx'});
  fs.renameSync(temporary, target);
}

try {
  main();
} catch (_) {
  process.stderr.write(`ONLYOFFICE worker initialization refused: ${stage}.\n`);
  process.exit(78);
}
