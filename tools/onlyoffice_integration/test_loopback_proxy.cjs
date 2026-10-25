"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {proxy, requestPath, requestHeaders, responseHeaders} = require("./loopback_proxy.cjs");

test("relative fixture paths preserve the signed query but cannot select another origin", () => {
  assert.equal(requestPath("/bucket/report.docx?signature=fixture", 3900), "/bucket/report.docx?signature=fixture");
  for (const value of ["https://other.example/file", "//other.example/file", "/\\other.example/file", "/a\r\nHost: other", ""]) {
    assert.throws(() => requestPath(value, 3900));
  }
  assert.throws(() => proxy(80), /Unknown fixture proxy/);
});

test("upstream redirects stay relative to the approved loopback origin", () => {
  for (const location of ["/cache/file", "http://localhost:8081/cache/file"]) {
    assert.equal(responseHeaders({location}, 8081).location, "/cache/file");
  }
  for (const location of ["https://other.example", "//other.example", "http://user@localhost:8081/file"]) {
    assert.throws(() => responseHeaders({location}, 8081));
  }
});

test("the fixture host is validated while session headers retain their values", () => {
  assert.equal(requestHeaders({host: "localhost:8081", cookie: "session=fixture"}, 8081).cookie, "session=fixture");
  assert.throws(() => requestHeaders({host: "other.example"}, 8081));
});

test("only known response headers cross the proxy without object prototypes or invalid values", () => {
  const headers = JSON.parse('{"content-type":"application/json","__proto__":{"polluted":true},"constructor":"unsafe"}');
  const result = responseHeaders(headers, 8081);
  assert.equal(Object.getPrototypeOf(result), null);
  assert.deepEqual(Object.keys(result), ["content-type"]);
  assert.equal({}.polluted, undefined);
  assert.throws(() => responseHeaders({"content-type":"text/plain\r\nLocation: https://other.example"}, 8081));
});
