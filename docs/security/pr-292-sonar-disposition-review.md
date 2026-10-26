# PR #292 Sonar disposition review

**PENDING OWNER APPROVAL. No risk is accepted and no Sonar status is changed by this document.**

The reviewed starting revision is `5b4279927f9c13143e6e5719a74aa0f470d7e20a`. Current Sonar reports zero bugs, seven OPEN vulnerabilities, 58 smells, Security D and gate FAIL; coverage 85.7% and duplication 0.1% pass. [Exact messages, severities and complete supplied flows](../integration/evidence/171-203-230-206/approval-sync/sonar-before.json). All seven supplied `flows` arrays are empty: these are pattern-based findings, not missing taint traces. Manual data-flow analysis follows for every finding.

The source supports four FALSE POSITIVE recommendations and three narrowly scoped ACCEPT proposals. The owner explicitly required outbound isolation, without approving a Sonar disposition. A basic Podman `internal=true` bridge blocked outbound traffic but admitted traffic from another bridge ([negative control](../integration/evidence/171-203-230-206/approval-sync/network-isolation-before.json)). The fixture now creates an owned `--internal --opt isolate=strict` bridge before Compose, verifies live engine metadata and every running peer, and fails closed on a weaker network. A controlled outside peer could reach all three examined services before strict isolation and could reach none afterward; owned same-bridge peers remained reachable. The outside canary was reachable from its own nonisolated positive-control network, while fixture peers had no default IPv4 route and could not connect to it. IPv6 was disabled on the bridge. [Sanitized live boundary results](../integration/evidence/171-203-230-206/approval-sync/network-isolation.json). The three HTTP operations remain plaintext, so they are eligible only for **PROPOSED ACCEPT**, subject to every condition below and an explicit attributable owner decision. No risk has been accepted.

The final boundary probe was repeated after the second normal `origin/main` merge (`029b979d1945484dbb720088dd77b4993a4ff2ad`) and the CloudBeaver test-fixture correction (`66eadeb831d58e787e6bc59f8c32f1917f62dfe8`). Browser, page-browser and Document Server all failed to reach a working outside canary; an outside peer could not reach Document Server, Garage or browser-control; owned peers could reach those services. Every inspected fixture member had one network, no published port and no default IPv4 route. The complete local regression receipts, including the 1,846-test Odoo run, real 27-editor regression, four real callback saves and Rust desktop observer, are in [post-merge local results](../integration/evidence/171-203-230-206/approval-sync/postmerge-local-results.json). These results preserve the 4/3 recommendations but do not grant approval or attest future fixture changes.

## Decision matrix

| Finding | Rule | Proposed Decision | Technical Evidence | Residual Risk | Required Approval | Status |
| --- | --- | --- | --- | --- | --- | --- |
| `AaF2G1TlIES1tmkRiAIQ` | `javascript:S4790` (CRITICAL) | FALSE POSITIVE | [Public WebSocket nonce handshake](#websocket) | No applicable vulnerable operation at this location; scoped assumptions below. | Security owner TBD; no approval received | PROPOSED FALSE POSITIVE |
| `AaF2G1X8IES1tmkRiAIS` | `javascript:S5332` (MINOR) | FALSE POSITIVE | [Expected Garage origin assertion](#test-garage) | No applicable vulnerable operation at this location; scoped assumptions below. | Security owner TBD; no approval received | PROPOSED FALSE POSITIVE |
| `AaF2G1X8IES1tmkRiAIT` | `javascript:S5332` (MINOR) | FALSE POSITIVE | [Expected editor origin assertion](#test-editor) | No applicable vulnerable operation at this location; scoped assumptions below. | Security owner TBD; no approval received | PROPOSED FALSE POSITIVE |
| `AaF2G1X8IES1tmkRiAIV` | `javascript:S5332` (MINOR) | FALSE POSITIVE | [Expected origin inside transport mock](#test-mock) | No applicable vulnerable operation at this location; scoped assumptions below. | Security owner TBD; no approval received | PROPOSED FALSE POSITIVE |
| `AaF2G1TlIES1tmkRiAIM` | `javascript:S5332` (MINOR) | ACCEPT within verified fixture scope | [Editor fixture HTTP](#http-editor) | Plaintext capabilities/data, tampering/replay, peer/host compromise and availability. | Security owner TBD; no approval received | PROPOSED ACCEPT |
| `AaF2G1TlIES1tmkRiAIN` | `javascript:S5332` (MINOR) | ACCEPT within verified fixture scope | [Browser-to-Garage fixture HTTP](#http-garage) | Plaintext capabilities/data, tampering/replay, peer/host compromise and availability. | Security owner TBD; no approval received | PROPOSED ACCEPT |
| `AaF0FHq1vCiqu-XFDLDC` | `python:S5332` (MINOR) | ACCEPT within verified fixture scope | [Document Server storage adapter HTTP](#http-python) | Plaintext capabilities/data, tampering/replay, peer/host compromise and availability. | Security owner TBD; no approval received | PROPOSED ACCEPT |

## Evidence and approval boundary

Read-only GitHub issue discussions for #171/#203/#230/#206 and PR #292 comments/reviews contain no explicit finding-specific disposition approval. Bot quality/naming comments and implementation handoffs are not security-owner decisions. No person is inferred to be the risk owner from Git authorship. No Sonar transition API is used; no exclusions, thresholds, required checks or scanners are changed.

Executed before synchronization: seven Node proxy tests, seven Python storage tests and 39 infrastructure/operator tests; exact command receipts are in the linked evidence directory. Post-sync fast contracts, strict-network 27-editor regression, four all-format callback saves and four real browser-page cases pass in a fresh owned project. The effective supervised 21-minute callback and 604800-second retention settings pass again. [Sanitized bidirectional bridge proof](../integration/evidence/171-203-230-206/approval-sync/network-isolation.json) includes all live peers and a working outside-network positive control. [Listener proof](../integration/evidence/171-203-230-206/approval-sync/loopback-listeners.json) confirms local success and same-bridge peer refusal on the three adapter sockets. Read-only live-environment/mount assertions found only the fixed disposable fixture credential values, no unreviewed sensitive variable names, and checkout/local named-volume mounts ([sanitized provenance](../integration/evidence/171-203-230-206/approval-sync/fixture-provenance.json)); this cannot attest future data provenance or a compromised trusted host. Control/upstream services intentionally remain reachable by owned same-bridge peers; loopback refusal alone would not establish that larger boundary. Host/container markers alone prove neither ownership nor isolation; the runner inspects actual engine metadata and fails closed on weaker options or unknown peers.

The production image/manifest review finds no fixture-proxy deployment: Odoo copies core modules/config/dependencies, and ONLYOFFICE production candidates declare HTTPS/443 and canonical runtime assets. This is source/configuration evidence, not a production inspection or assurance of CNI, logging or production reachability. The earlier ordinary bridge allowed outbound routing, and a basic internal bridge admitted cross-bridge ingress. [Podman's bridge option reference](https://docs.podman.io/en/v6.0.2/markdown/podman-network-create.1.html) describes `isolate=strict` as blocking traffic to and from other bridges; the new strict bridge passed independent controlled probes. This is not proof against a compromised trusted host or production reachability outside the fixture. No production endpoint or credential is probed.

Status vocabulary: PROPOSED FALSE POSITIVE, PROPOSED ACCEPT, FIX REQUIRED, NEEDS INVESTIGATION, APPROVED, REJECTED. APPROVED/REJECTED require an attributable owner decision with scope/date; none exists here. Applying a disposition is a separate administrative action after authorization.

## Public WebSocket nonce handshake

<a id="websocket"></a>

| Review field | Record |
| --- | --- |
| Sonar key | `AaF2G1TlIES1tmkRiAIQ` |
| Rule / severity | `javascript:S4790` / CRITICAL |
| Source | [tools/onlyoffice_integration/loopback_proxy.cjs:155](../../tools/onlyoffice_integration/loopback_proxy.cjs#L155) |
| Scanner message | Make sure this weak hash algorithm is not used in a sensitive context here. |
| Supplied complete taint flow | `[]` — no flow supplied; manual trace below |
| Current Sonar status | OPEN; unchanged |
| Recommended decision / eligibility | FALSE POSITIVE / PROPOSED FALSE POSITIVE |
| Security owner approval | PENDING; named authorized approver not yet identified |

**Operation and manual source-to-sink analysis.** The only SHA-1 call receives Sec-WebSocket-Key plus the fixed RFC GUID. The local digest is compared only with Sec-WebSocket-Accept inside the 101 upgrade handler. It is not exported, persisted or applied to passwords, JWTs, credentials, document bytes or digital signatures. JWT authentication remains HS256 in services/onlyoffice_jwt.py; object integrity remains SHA-256 in services/laboratory_bucket.py. This is protocol validation, not authentication or integrity protection.

```javascript
    }
    const upstream = http.request(url, {method: "GET", headers});
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
```

**Executed positive and negative regressions.** Positive: independent RFC nonce/accept vector and a working HTTP/WebSocket tunnel. Negative: wrong accept, invalid key/version/method, body-bearing and storage upgrades are rejected. The seven Node cases pass. [Command receipts](../integration/evidence/171-203-230-206/approval-sync/). These tests support the technical assessment; they are not owner approval.

**Trust boundaries, uncertainty and limitations.** No SHA-1 cryptographic security property is needed here. A malicious peer can compute this public response; authorization and transport confidentiality are separate controls. The test title using “authenticates” means protocol response validation, not identity authentication.

**Protocol proof.** [RFC 6455 §4.2.2](https://www.rfc-editor.org/rfc/rfc6455.html#section-4.2.2) requires the public nonce/GUID SHA-1/Base64 calculation. [§10.8](https://www.rfc-editor.org/rfc/rfc6455.html#section-10.8) explains that this handshake does not depend on SHA-1 collision/second-preimage resistance. The result never enters password storage, JWT signing, user authentication, credential protection, document checksums or security-sensitive digital signatures. Replacing it with SHA-256 breaks the protocol. Approval applies only to this exact operation, not to other SHA-1 uses.

**Required approval and invalidation.** The named security owner must explicitly approve this key and this proof. Administrative disposition is separate and not performed. If the operation begins handling credentials/integrity data, opening a real external network destination, or changes beyond the analyzed context, reopen/reassess rather than reusing this recommendation.

## Expected Garage origin assertion

<a id="test-garage"></a>

| Review field | Record |
| --- | --- |
| Sonar key | `AaF2G1X8IES1tmkRiAIS` |
| Rule / severity | `javascript:S5332` / MINOR |
| Source | [tools/onlyoffice_integration/test_loopback_proxy.cjs:16](../../tools/onlyoffice_integration/test_loopback_proxy.cjs#L16) |
| Scanner message | Using http protocol is insecure. Use https instead. |
| Supplied complete taint flow | `[]` — no flow supplied; manual trace below |
| Current Sonar status | OPEN; unchanged |
| Recommended decision / eligibility | FALSE POSITIVE / PROPOSED FALSE POSITIVE |
| Security owner approval | PENDING; named authorized approver not yet identified |

**Operation and manual source-to-sink analysis.** The flagged HTTP literal is an expected value passed to assert.equal after requestURL constructs a URL. This test never opens a socket. Even proxy(80) must throw before listening. No sensitive data is transmitted by the flagged operation.

```javascript
test("fixed upstream authority and presigned query survive without normalization", () => {
  const path = "/laboratory-files-fixture/report%20one.docx?signature=A%2FB%2B&host=other.example";
  const url = requestURL(path, 3900);
  assert.equal(url.origin, "http://garage:3900");
  assert.equal(url.pathname + url.search, path);
  assert.equal(requestURL("/web-apps/file?url=https%3A%2F%2Fother.example", 8081).origin, "http://documentserver");
  assert.equal(requestPath("/laboratory-files/a%25b", 3900), "/laboratory-files/a%25b");
  assert.throws(() => proxy(80), /Unknown fixture proxy/);
```

**Executed positive and negative regressions.** Positive: owned bucket path and signed query retain bytes and origin. Negative: absolute/authority-confused targets, unsupported proxy ports, traversal and separators are rejected by the adjacent cases. Seven Node cases pass. [Command receipts](../integration/evidence/171-203-230-206/approval-sync/). These tests support the technical assessment; they are not owner approval.

**Trust boundaries, uncertainty and limitations.** This recommendation applies to this assertion, not to the real Garage transport. Moving the literal into a network call would invalidate it.

**Required approval and invalidation.** The named security owner must explicitly approve this key and this proof. Administrative disposition is separate and not performed. If the operation begins handling credentials/integrity data, opening a real external network destination, or changes beyond the analyzed context, reopen/reassess rather than reusing this recommendation.

## Expected editor origin assertion

<a id="test-editor"></a>

| Review field | Record |
| --- | --- |
| Sonar key | `AaF2G1X8IES1tmkRiAIT` |
| Rule / severity | `javascript:S5332` / MINOR |
| Source | [tools/onlyoffice_integration/test_loopback_proxy.cjs:18](../../tools/onlyoffice_integration/test_loopback_proxy.cjs#L18) |
| Scanner message | Using http protocol is insecure. Use https instead. |
| Supplied complete taint flow | `[]` — no flow supplied; manual trace below |
| Current Sonar status | OPEN; unchanged |
| Recommended decision / eligibility | FALSE POSITIVE / PROPOSED FALSE POSITIVE |
| Security owner approval | PENDING; named authorized approver not yet identified |

**Operation and manual source-to-sink analysis.** The flagged HTTP literal is an expected url.origin in the same pure URL-construction test. A query containing another encoded URL cannot change the authority. requestURL constructs a URL without performing network I/O.

```javascript
test("fixed upstream authority and presigned query survive without normalization", () => {
  const path = "/laboratory-files-fixture/report%20one.docx?signature=A%2FB%2B&host=other.example";
  const url = requestURL(path, 3900);
  assert.equal(url.origin, "http://garage:3900");
  assert.equal(url.pathname + url.search, path);
  assert.equal(requestURL("/web-apps/file?url=https%3A%2F%2Fother.example", 8081).origin, "http://documentserver");
  assert.equal(requestPath("/laboratory-files/a%25b", 3900), "/laboratory-files/a%25b");
  assert.throws(() => proxy(80), /Unknown fixture proxy/);
```

**Executed positive and negative regressions.** Positive: expected fixed Document Server origin. Negative: foreign origins/redirects and malformed targets are refused; the seven Node cases pass. [Command receipts](../integration/evidence/171-203-230-206/approval-sync/). These tests support the technical assessment; they are not owner approval.

**Trust boundaries, uncertainty and limitations.** This recommendation applies only to the comparison. It does not classify live editor HTTP as safe or encrypted.

**Required approval and invalidation.** The named security owner must explicitly approve this key and this proof. Administrative disposition is separate and not performed. If the operation begins handling credentials/integrity data, opening a real external network destination, or changes beyond the analyzed context, reopen/reassess rather than reusing this recommendation.

## Expected origin inside transport mock

<a id="test-mock"></a>

| Review field | Record |
| --- | --- |
| Sonar key | `AaF2G1X8IES1tmkRiAIV` |
| Rule / severity | `javascript:S5332` / MINOR |
| Source | [tools/onlyoffice_integration/test_loopback_proxy.cjs:76](../../tools/onlyoffice_integration/test_loopback_proxy.cjs#L76) |
| Scanner message | Using http protocol is insecure. Use https instead. |
| Supplied complete taint flow | `[]` — no flow supplied; manual trace below |
| Current Sonar status | OPEN; unchanged |
| Recommended decision / eligibility | FALSE POSITIVE / PROPOSED FALSE POSITIVE |
| Security owner approval | PENDING; named authorized approver not yet identified |

**Operation and manual source-to-sink analysis.** The literal is asserted inside a per-test http.request mock. The saved original request is invoked with a literal 127.0.0.1 hostname and an ephemeral local server port. The logical Document Server origin is not used as the network destination. Both actual test listeners bind loopback and are closed during cleanup; bodies and headers are fixed synthetic values.

```javascript
async function fixture(t, handler) {
  const original = http.request;
  const upstream = http.createServer(handler).listen(0, "127.0.0.1");
  await once(upstream, "listening");
  const calls = [];
  t.mock.method(http, "request", (url, options, callback) => {
    assert.ok(url instanceof URL);
    assert.equal(url.origin, "http://documentserver");
    calls.push(url.pathname + url.search);
    return original({hostname: "127.0.0.1", port: upstream.address().port,
      path: url.pathname + url.search, ...options}, callback);
  });
  const server = proxy(8081, 0);
  await once(server, "listening");
  t.after(() => { server.closeAllConnections(); server.close(); upstream.closeAllConnections(); upstream.close(); });
  return {upstream, server, calls, original};
```

**Executed positive and negative regressions.** Positive: exact bytes/status and approved redirects cross the actual loopback test transport. Negative: external redirects produce 502 before headers, rejected paths never reach the upstream, and invalid WebSocket accepts do not establish a tunnel. Seven Node cases pass. [Command receipts](../integration/evidence/171-203-230-206/approval-sync/). These tests support the technical assessment; they are not owner approval.

**Trust boundaries, uncertainty and limitations.** The local test does use HTTP intentionally, but the flagged literal is an assertion-only value and has no credential or external network sink. This is not an exception for arbitrary real HTTP requests.

**Required approval and invalidation.** The named security owner must explicitly approve this key and this proof. Administrative disposition is separate and not performed. If the operation begins handling credentials/integrity data, opening a real external network destination, or changes beyond the analyzed context, reopen/reassess rather than reusing this recommendation.

## Editor fixture HTTP

<a id="http-editor"></a>

| Review field | Record |
| --- | --- |
| Sonar key | `AaF2G1TlIES1tmkRiAIM` |
| Rule / severity | `javascript:S5332` / MINOR |
| Source | [tools/onlyoffice_integration/loopback_proxy.cjs:7](../../tools/onlyoffice_integration/loopback_proxy.cjs#L7) |
| Scanner message | Using http protocol is insecure. Use https instead. |
| Supplied complete taint flow | `[]` — no flow supplied; manual trace below |
| Current Sonar status | OPEN; unchanged |
| Recommended decision / eligibility | ACCEPT within verified fixture scope / PROPOSED ACCEPT |
| Security owner approval | PENDING; named authorized approver not yet identified |

**Operation and manual source-to-sink analysis.** page-browser exposes the proxy at 127.0.0.1:8081 and forwards to the fixed owned Document Server on port 80. Host, authority, path, redirect and upgrade validation constrain traffic. Authorization and Cookie headers are deliberately preserved for this editor upstream. A plaintext connection really occurs, so FALSE POSITIVE is not appropriate.

```javascript
const TARGETS = new Map([
  [8081, {upstream: "http://documentserver", origin: "http://localhost:8081"}],
  [3900, {upstream: "http://garage:3900", origin: "http://localhost:3900"}],
]);
const REQUEST_HEADERS = ["host", "accept", "accept-encoding", "accept-language", "authorization", "cache-control",
  "content-length", "content-type", "cookie", "if-modified-since", "if-none-match", "origin", "range", "referer",
  "sec-websocket-key", "sec-websocket-version", "sec-websocket-extensions", "sec-websocket-protocol", "user-agent"];
const RESPONSE_HEADERS = ["accept-ranges", "access-control-allow-credentials", "access-control-allow-origin",
  "cache-control", "content-disposition", "content-encoding", "content-length", "content-range", "content-security-policy",
  "content-type", "date", "etag", "expires", "last-modified", "set-cookie", "vary", "x-content-type-options", "x-frame-options"];
const UPGRADE_HEADERS = ["sec-websocket-accept", "sec-websocket-protocol", "sec-websocket-extensions"];
```

**Executed positive and negative regressions.** Node positive/negative routing, headers, redirects and WebSocket cases pass. Fresh strict-network real DOCX/XLSX/PPTX editor-page saves and callback/idempotency/fresh-token cases pass. Bidirectional outside-canary and same-bridge positive controls demonstrate the required fixture boundary; they do not encrypt the HTTP hop. [Command receipts](../integration/evidence/171-203-230-206/approval-sync/). These tests support the technical assessment; they are not owner approval.

**Trust boundaries, uncertainty and limitations.** Synthetic editor JWTs, cookies, capability URLs and Office bytes can be observed, replayed within normal validity or modified by a compromised same-namespace process, trusted host or bridge observer.

**Confidentiality.** Fixture objects and any bearer tokens/presigned URLs in this transport are visible to an observer on the permitted path. Editor cookies/JWTs are preserved only for the Document Server path; storage forwarding drops Authorization/Cookie, but signed query capabilities remain sensitive within the fixture.

**Integrity.** A compromised host/namespace/bridge peer can tamper with responses and replay still-valid capabilities. Strict JWT/presigned verification and immutable version checks are retained, but they do not make every plaintext response trustworthy. Known disposable peer/admin credentials permit fixture-state modification; synthetic object hashes help detect differences, not prevent every tampering attempt.

**Availability.** Trusted-peer compromise, request flooding or browser-control abuse can exhaust resources, disrupt saves or alter/delete fixture data. Bounded test deadlines, retained evidence/volumes, ownership guards and recovery/restart checks limit operational impact; the acceptance must include this residual test-data availability risk.

**Network facts.** Proxy binds are loopback. Control/upstream services deliberately listen on their private interfaces and remain reachable by trusted same-network peers. No published ports or host network are permitted. The earlier ordinary bridge and then basic internal bridge failed the required isolation boundary. The owned strict bridge now blocks both directions to other bridges in controlled tests, with same-bridge positive controls and no default IPv4 route. The runner verifies the live option, ownership, members and publications before acceptance. This local proof does not establish production CNI or host compromise resistance.

**Mandatory scope — each condition is binding.**

| Required constraint | Proof required / invalidation |
| --- | --- |
| Synthetic test data only | Fresh owned test databases and generated marker documents; no imported real documents. |
| Disposable credentials only | Known fixture credentials/ephemeral test keys; no user browser profile or production trust material. |
| Trusted project-controlled peers | Inventory every network member; refuse unknown peers or peers attached to another network. |
| Fixed owned upstream destinations | Resolve fixed logical names to inspected owned containers; request input never chooses authority. |
| No production credentials | Inspect declared environment/mount names without publishing values; refuse production secret/profile mounts. |
| No production data | Use only fixture-created objects/databases; owner must attest provenance if any external content is introduced. |
| No production network attachment | Only the owned internal test bridge; refuse host/shared/external or multiple network attachments. |
| No publicly published ports | No HostConfig port mappings, service port publications or host networking. |
| Loopback or demonstrably isolated listeners | Actual loopback proxy sockets; other service listeners remain within the owned internal namespace/network. |
| No exposure to untrusted networks | The owned strict bridge must block inbound and outbound cross-bridge routing. Verify actual engine options, routes, blocked outside canary and working same-bridge/outside control peers on each infrastructure change. |
| No production reuse | Scope is only tools/onlyoffice_integration and its controlled test execution; any production reuse invalidates the exception. |

**Compensating controls.** Strict fixed-origin/path/redirect/header rules; real service JWT authorization and immutable version semantics; source/data provenance checks; loopback listeners; no host publication; owned internal bridge and one-network peers; bounded test execution; synthetic credentials; retained recovery evidence; no production packaging. The controls apply only while the live strict-bridge proof remains valid; they do not encrypt the fixture hop.

**Acceptance metadata.**

| Metadata | Value |
| --- | --- |
| Accountable risk owner | TBD — must be explicitly named; not inferred from Git identity |
| Required approver | TBD — authorized security owner |
| Approval / decision date | PENDING; no attributable approval exists |
| Exact scope | This finding, controlled ONLYOFFICE test fixture, generated synthetic documents, disposable credentials, fixed owned endpoints and verified internal network only |
| Residual risk owner accepts | Disclosure/replay/tampering of fixture capabilities/bytes; compromised trusted host/peer; disruption, flooding and retained fixture-data availability |
| Expiration / review | Proposal only: 30 calendar days after approval or immediately on a scope/control change, whichever occurs first; owner must set the actual date |
| Invalidation | Any real data/credential, unknown peer, extra/external/host network, published port, untrusted ingress/egress, destination/code/image/dependency/mount change or production reuse |
| Automatic fallback | FIX / REASSESS; stop relying on the proposed acceptance if any required condition cannot be demonstrated or maintained |
| Remediation alternative | Reviewed TLS with validated identities and/or stronger network isolation; never an undocumented exception |
| Change verification | Reinspect actual listeners/port bindings/network members/routes, DNS ownership, secret/data provenance; rerun outside-canary positive/negative controls and affected HTTP/WebSocket/JWT/save/migration regressions |
| Administrative disposition | Separate authorized Sonar action only after explicit per-finding owner approval; not performed here |

## Browser-to-Garage fixture HTTP

<a id="http-garage"></a>

| Review field | Record |
| --- | --- |
| Sonar key | `AaF2G1TlIES1tmkRiAIN` |
| Rule / severity | `javascript:S5332` / MINOR |
| Source | [tools/onlyoffice_integration/loopback_proxy.cjs:8](../../tools/onlyoffice_integration/loopback_proxy.cjs#L8) |
| Scanner message | Using http protocol is insecure. Use https instead. |
| Supplied complete taint flow | `[]` — no flow supplied; manual trace below |
| Current Sonar status | OPEN; unchanged |
| Recommended decision / eligibility | ACCEPT within verified fixture scope / PROPOSED ACCEPT |
| Security owner approval | PENDING; named authorized approver not yet identified |

**Operation and manual source-to-sink analysis.** page-browser listens at 127.0.0.1:3900 and forwards only to owned Garage:3900. Owned bucket paths and canonical targets are required; Authorization and Cookie headers are stripped. Presigned query strings are bearer capabilities and file bytes still cross the bridge in cleartext. Removing headers does not provide confidentiality.

```javascript
const TARGETS = new Map([
  [8081, {upstream: "http://documentserver", origin: "http://localhost:8081"}],
  [3900, {upstream: "http://garage:3900", origin: "http://localhost:3900"}],
]);
const REQUEST_HEADERS = ["host", "accept", "accept-encoding", "accept-language", "authorization", "cache-control",
  "content-length", "content-type", "cookie", "if-modified-since", "if-none-match", "origin", "range", "referer",
  "sec-websocket-key", "sec-websocket-version", "sec-websocket-extensions", "sec-websocket-protocol", "user-agent"];
const RESPONSE_HEADERS = ["accept-ranges", "access-control-allow-credentials", "access-control-allow-origin",
  "cache-control", "content-disposition", "content-encoding", "content-length", "content-range", "content-security-policy",
  "content-type", "date", "etag", "expires", "last-modified", "set-cookie", "vary", "x-content-type-options", "x-frame-options"];
const UPGRADE_HEADERS = ["sec-websocket-accept", "sec-websocket-protocol", "sec-websocket-extensions"];
```

**Executed positive and negative regressions.** Node tests verify the fixed origin, signed query byte preservation, bucket/path validation, header stripping and redirect refusal. Real all-format saves/downloads are rerun after synchronization and isolation. [Command receipts](../integration/evidence/171-203-230-206/approval-sync/). These tests support the technical assessment; they are not owner approval.

**Trust boundaries, uncertainty and limitations.** A bridge/host observer can obtain presigned capabilities or modify synthetic bytes. Known disposable Garage credentials and reachable admin/RPC services also permit fixture-data modification or loss by a compromised trusted peer.

**Confidentiality.** Fixture objects and any bearer tokens/presigned URLs in this transport are visible to an observer on the permitted path. Editor cookies/JWTs are preserved only for the Document Server path; storage forwarding drops Authorization/Cookie, but signed query capabilities remain sensitive within the fixture.

**Integrity.** A compromised host/namespace/bridge peer can tamper with responses and replay still-valid capabilities. Strict JWT/presigned verification and immutable version checks are retained, but they do not make every plaintext response trustworthy. Known disposable peer/admin credentials permit fixture-state modification; synthetic object hashes help detect differences, not prevent every tampering attempt.

**Availability.** Trusted-peer compromise, request flooding or browser-control abuse can exhaust resources, disrupt saves or alter/delete fixture data. Bounded test deadlines, retained evidence/volumes, ownership guards and recovery/restart checks limit operational impact; the acceptance must include this residual test-data availability risk.

**Network facts.** Proxy binds are loopback. Control/upstream services deliberately listen on their private interfaces and remain reachable by trusted same-network peers. No published ports or host network are permitted. The earlier ordinary bridge and then basic internal bridge failed the required isolation boundary. The owned strict bridge now blocks both directions to other bridges in controlled tests, with same-bridge positive controls and no default IPv4 route. The runner verifies the live option, ownership, members and publications before acceptance. This local proof does not establish production CNI or host compromise resistance.

**Mandatory scope — each condition is binding.**

| Required constraint | Proof required / invalidation |
| --- | --- |
| Synthetic test data only | Fresh owned test databases and generated marker documents; no imported real documents. |
| Disposable credentials only | Known fixture credentials/ephemeral test keys; no user browser profile or production trust material. |
| Trusted project-controlled peers | Inventory every network member; refuse unknown peers or peers attached to another network. |
| Fixed owned upstream destinations | Resolve fixed logical names to inspected owned containers; request input never chooses authority. |
| No production credentials | Inspect declared environment/mount names without publishing values; refuse production secret/profile mounts. |
| No production data | Use only fixture-created objects/databases; owner must attest provenance if any external content is introduced. |
| No production network attachment | Only the owned internal test bridge; refuse host/shared/external or multiple network attachments. |
| No publicly published ports | No HostConfig port mappings, service port publications or host networking. |
| Loopback or demonstrably isolated listeners | Actual loopback proxy sockets; other service listeners remain within the owned internal namespace/network. |
| No exposure to untrusted networks | The owned strict bridge must block inbound and outbound cross-bridge routing. Verify actual engine options, routes, blocked outside canary and working same-bridge/outside control peers on each infrastructure change. |
| No production reuse | Scope is only tools/onlyoffice_integration and its controlled test execution; any production reuse invalidates the exception. |

**Compensating controls.** Strict fixed-origin/path/redirect/header rules; real service JWT authorization and immutable version semantics; source/data provenance checks; loopback listeners; no host publication; owned internal bridge and one-network peers; bounded test execution; synthetic credentials; retained recovery evidence; no production packaging. The controls apply only while the live strict-bridge proof remains valid; they do not encrypt the fixture hop.

**Acceptance metadata.**

| Metadata | Value |
| --- | --- |
| Accountable risk owner | TBD — must be explicitly named; not inferred from Git identity |
| Required approver | TBD — authorized security owner |
| Approval / decision date | PENDING; no attributable approval exists |
| Exact scope | This finding, controlled ONLYOFFICE test fixture, generated synthetic documents, disposable credentials, fixed owned endpoints and verified internal network only |
| Residual risk owner accepts | Disclosure/replay/tampering of fixture capabilities/bytes; compromised trusted host/peer; disruption, flooding and retained fixture-data availability |
| Expiration / review | Proposal only: 30 calendar days after approval or immediately on a scope/control change, whichever occurs first; owner must set the actual date |
| Invalidation | Any real data/credential, unknown peer, extra/external/host network, published port, untrusted ingress/egress, destination/code/image/dependency/mount change or production reuse |
| Automatic fallback | FIX / REASSESS; stop relying on the proposed acceptance if any required condition cannot be demonstrated or maintained |
| Remediation alternative | Reviewed TLS with validated identities and/or stronger network isolation; never an undocumented exception |
| Change verification | Reinspect actual listeners/port bindings/network members/routes, DNS ownership, secret/data provenance; rerun outside-canary positive/negative controls and affected HTTP/WebSocket/JWT/save/migration regressions |
| Administrative disposition | Separate authorized Sonar action only after explicit per-finding owner approval; not performed here |

## Document Server storage adapter HTTP

<a id="http-python"></a>

| Review field | Record |
| --- | --- |
| Sonar key | `AaF0FHq1vCiqu-XFDLDC` |
| Rule / severity | `python:S5332` / MINOR |
| Source | [tools/onlyoffice_integration/loopback_storage_proxy.py:84](../../tools/onlyoffice_integration/loopback_storage_proxy.py#L84) |
| Scanner message | Using HTTP protocol is insecure. Use HTTPS instead. |
| Supplied complete taint flow | `[]` — no flow supplied; manual trace below |
| Current Sonar status | OPEN; unchanged |
| Recommended decision / eligibility | ACCEPT within verified fixture scope / PROPOSED ACCEPT |
| Security owner approval | PENDING; named authorized approver not yet identified |

**Operation and manual source-to-sink analysis.** An explicitly enabled adapter in the Document Server namespace binds 127.0.0.1:3900 and issues GET only to fixed owned Garage:3900. It forwards Host only, validates encoded paths/query byte equality, and refuses unknown Host values. The environment/runtime markers are startup intent checks, not isolation or ownership proof.

```python
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        host = self.headers.get("Host")
        if host not in ("localhost:3900", "127.0.0.1:3900"):
            self.send_error(400)
            return
        try:
            path = storage_path(self.path)
        except ValueError:
            self.send_error(400)
            return
        connection = http.client.HTTPConnection("garage", 3900, timeout=30)
        try:
            connection.request("GET", path, headers={"Host": host})
            upstream = connection.getresponse()
            self.send_response(upstream.status)
            for name, value in upstream.getheaders():
                if name.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(name, value)
            self.end_headers()
            while chunk := upstream.read(65536):
                self.wfile.write(chunk)
        finally:
            connection.close()

    def log_message(self, *_args):
        return


def main():
    if os.environ.get("MEDILAB_ONLYOFFICE_STORAGE_FIXTURE") != "isolated-owned":
        raise RuntimeError("Enable only in an explicitly owned isolated fixture.")
    if not os.path.exists("/run/.containerenv") and not os.path.exists("/.dockerenv"):
        raise RuntimeError("The storage adapter requires container runtime markers.")
    ThreadingHTTPServer(("127.0.0.1", 3900), Handler).serve_forever()


if __name__ == "__main__":
    main()
```

**Executed positive and negative regressions.** Seven Python storage tests pass, including live loopback forwarding, caller credential stripping, malformed/nested traversal and canonical signed-query cases, wrong Host, and disabled/non-container startup. The post-sync listener probe shows success only inside the Document Server namespace and refusal from a separate owned peer. The strict bridge passes bidirectional outside-canary checks. [Command receipts](../integration/evidence/171-203-230-206/approval-sync/). These tests support the technical assessment; they are not owner approval.

**Trust boundaries, uncertainty and limitations.** Processes inside Document Server can reach its loopback. Presigned URLs and synthetic objects traverse the bridge in plaintext. A compromised peer/host can disclose, replay or alter traffic, disrupt the adapter or affect fixture data.

**Confidentiality.** Fixture objects and any bearer tokens/presigned URLs in this transport are visible to an observer on the permitted path. Editor cookies/JWTs are preserved only for the Document Server path; storage forwarding drops Authorization/Cookie, but signed query capabilities remain sensitive within the fixture.

**Integrity.** A compromised host/namespace/bridge peer can tamper with responses and replay still-valid capabilities. Strict JWT/presigned verification and immutable version checks are retained, but they do not make every plaintext response trustworthy. Known disposable peer/admin credentials permit fixture-state modification; synthetic object hashes help detect differences, not prevent every tampering attempt.

**Availability.** Trusted-peer compromise, request flooding or browser-control abuse can exhaust resources, disrupt saves or alter/delete fixture data. Bounded test deadlines, retained evidence/volumes, ownership guards and recovery/restart checks limit operational impact; the acceptance must include this residual test-data availability risk.

**Network facts.** Proxy binds are loopback. Control/upstream services deliberately listen on their private interfaces and remain reachable by trusted same-network peers. No published ports or host network are permitted. The earlier ordinary bridge and then basic internal bridge failed the required isolation boundary. The owned strict bridge now blocks both directions to other bridges in controlled tests, with same-bridge positive controls and no default IPv4 route. The runner verifies the live option, ownership, members and publications before acceptance. This local proof does not establish production CNI or host compromise resistance.

**Mandatory scope — each condition is binding.**

| Required constraint | Proof required / invalidation |
| --- | --- |
| Synthetic test data only | Fresh owned test databases and generated marker documents; no imported real documents. |
| Disposable credentials only | Known fixture credentials/ephemeral test keys; no user browser profile or production trust material. |
| Trusted project-controlled peers | Inventory every network member; refuse unknown peers or peers attached to another network. |
| Fixed owned upstream destinations | Resolve fixed logical names to inspected owned containers; request input never chooses authority. |
| No production credentials | Inspect declared environment/mount names without publishing values; refuse production secret/profile mounts. |
| No production data | Use only fixture-created objects/databases; owner must attest provenance if any external content is introduced. |
| No production network attachment | Only the owned internal test bridge; refuse host/shared/external or multiple network attachments. |
| No publicly published ports | No HostConfig port mappings, service port publications or host networking. |
| Loopback or demonstrably isolated listeners | Actual loopback proxy sockets; other service listeners remain within the owned internal namespace/network. |
| No exposure to untrusted networks | The owned strict bridge must block inbound and outbound cross-bridge routing. Verify actual engine options, routes, blocked outside canary and working same-bridge/outside control peers on each infrastructure change. |
| No production reuse | Scope is only tools/onlyoffice_integration and its controlled test execution; any production reuse invalidates the exception. |

**Compensating controls.** Strict fixed-origin/path/redirect/header rules; real service JWT authorization and immutable version semantics; source/data provenance checks; loopback listeners; no host publication; owned internal bridge and one-network peers; bounded test execution; synthetic credentials; retained recovery evidence; no production packaging. The controls apply only while the live strict-bridge proof remains valid; they do not encrypt the fixture hop.

**Acceptance metadata.**

| Metadata | Value |
| --- | --- |
| Accountable risk owner | TBD — must be explicitly named; not inferred from Git identity |
| Required approver | TBD — authorized security owner |
| Approval / decision date | PENDING; no attributable approval exists |
| Exact scope | This finding, controlled ONLYOFFICE test fixture, generated synthetic documents, disposable credentials, fixed owned endpoints and verified internal network only |
| Residual risk owner accepts | Disclosure/replay/tampering of fixture capabilities/bytes; compromised trusted host/peer; disruption, flooding and retained fixture-data availability |
| Expiration / review | Proposal only: 30 calendar days after approval or immediately on a scope/control change, whichever occurs first; owner must set the actual date |
| Invalidation | Any real data/credential, unknown peer, extra/external/host network, published port, untrusted ingress/egress, destination/code/image/dependency/mount change or production reuse |
| Automatic fallback | FIX / REASSESS; stop relying on the proposed acceptance if any required condition cannot be demonstrated or maintained |
| Remediation alternative | Reviewed TLS with validated identities and/or stronger network isolation; never an undocumented exception |
| Change verification | Reinspect actual listeners/port bindings/network members/routes, DNS ownership, secret/data provenance; rerun outside-canary positive/negative controls and affected HTTP/WebSocket/JWT/save/migration regressions |
| Administrative disposition | Separate authorized Sonar action only after explicit per-finding owner approval; not performed here |

## Approval request summary

PENDING OWNER APPROVAL. Four findings have evidence-backed FALSE POSITIVE recommendations: AaF2G1TlIES1tmkRiAIQ, AaF2G1X8IES1tmkRiAIS, AaF2G1X8IES1tmkRiAIT, AaF2G1X8IES1tmkRiAIV. Three live-HTTP findings are intended ACCEPT candidates: AaF2G1TlIES1tmkRiAIM, AaF2G1TlIES1tmkRiAIN, AaF0FHq1vCiqu-XFDLDC. Live bidirectional strict-bridge isolation has been demonstrated locally; the three decisions remain PROPOSED ACCEPT pending individually attributed security-owner decisions and all scope conditions. If any condition fails, they revert to FIX / REASSESS. Name the accountable risk owner and security approver, approve/reject each key independently, set scope and review/expiration dates, and record residual CIA risk. No response or automated test result constitutes approval. No Sonar status, rule, exclusion or threshold is changed.

## Related documents

- [Integration acceptance](../integration/171-203-230-206-acceptance.md)
- [ONLYOFFICE operations](../infrastructure/onlyoffice.md)
- [Pending infrastructure decisions](../../questions/infrastructure.md)
- [Fixture instructions](../../tools/onlyoffice_integration/README.md)
