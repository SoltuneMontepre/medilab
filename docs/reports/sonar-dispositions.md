# Sonar dispositions

The owner authorized ignoring confirmed SonarQube false positives. `sonar-project.properties` scopes each exclusion to one rule and one file; other rules continue to scan those files. An exclusion does not approve arbitrary endpoints, untrusted command callers or weakened ownership checks. Review it again if a boundary below changes.

The local tools rely on the trust boundary of the [local setup security review](local-setup-security-review.md). Findings that need an owner decision stay open and are not listed here.

| Exclusion | Rule and file | Reason and required controls |
| --- | --- | --- |
| --- | --- | --- |
| localGarageOwner | python:S7608; tools/onlyoffice/verify.py | `ExpectedBucketOwner` checks AWS account identity, which the pinned local Garage does not enforce. The verifier requires the expected bucket, fixed http://garage:3900 origin, scoped signing credentials and a UUID-only disposable key. Cleanup requires an explicit valid identity and accepts only 404 as proof of absence. Do not add a fictitious AWS account ID. |
| fixedProxyRoutes | pythonsecurity:S5144; tools/onlyoffice/proxy.py | Request paths cannot select an upstream authority. `route` returns only fixed service tuples after exact Host/method/path checks. `safe_path` rejects absolute/network-path targets, traversal and recursive encoded separators. Redirects are validated and never followed by the proxy; upstream TLS is verified. |
| localComposeOperator | pythonsecurity:S8705; tools/scripts/local_compose.py | Explicit local operator arguments to container run/exec are an intentional CLI capability. The executable and Compose project/files are fixed, commands are allowlisted, identity overrides and down flags are refused, and subprocess receives an argument vector without a shell. This wrapper must not accept remote command input. |
| bootstrapOwnedArguments | pythonsecurity:S6350; tools/scripts/demo_bootstrap.py | Native subprocess arguments come from fixed command builders and validated private state, not an HTTP request. Format, exact config keys, generated volume names, project/worktree/owner and engine are checked before mutations. Private ancestor integrity and exclusive temporary writes protect the journal source. |
| editorOwnedArguments | pythonsecurity:S6350; tools/scripts/onlyoffice.py | The same validated state and fixed native command builders constrain editor operations. Captured command failures are redacted. Shell escaping or moving the subprocess sink would not add a control. |
| privateLocalPaths | pythonsecurity:S6549; tools/scripts/onlyoffice_state.py | Filesystem probes are local ownership checks without a remote response oracle. Supplied TLS paths must lexically match the expected owned path before probes. The managed ancestor chain, links/junctions, current-user ownership, POSIX modes and Windows ACLs remain checked. |
| fixedLoopbackHealth | pythonsecurity:S5144; tools/scripts/onlyoffice_checks.py | Public health probes connect only to literal 127.0.0.1. `validated_port` rejects nonnumeric/out-of-range saved ports before HTTPConnection. State cannot change the destination host, scheme or path. |
| metadataDenialProof | python:S1313; tools/scripts/check_onlyoffice_docker_network.py | 169.254.169.254 is the deliberate cloud metadata denial target. The synthetic network proof opens a bounded TCP connection and closes it without sending HTTP or reading metadata. Any reachability fails the isolation check. Replacing the literal would weaken that check. |
| metadataDenialCheck | python:S1313; tools/scripts/onlyoffice_checks.py | The runtime isolation check uses the same TCP-only metadata denial target, alongside backend/host targets and positive controls. It fails if the isolated Document Server namespace can reach any forbidden target. |
| expoAssetKey | typescript:S4790; src/applications/medilab-mobile/scripts/release/manifest.ts | The [Expo Updates protocol](https://docs.expo.dev/technical-specs/expo-updates-1/) names each asset by the `key` its application code references, and `expo-asset` references a bundled asset by the MD5 of its content. The MD5 is a lookup name, not an integrity check: the manifest's `hash` is SHA-256, which the client verifies, and the manifest itself is signed. |
| websocketAccept | javascript:S4790; tools/onlyoffice_integration/loopback_proxy.cjs | RFC 6455 defines `Sec-WebSocket-Accept` as the SHA-1 of the public client nonce and a fixed GUID. It is handshake framing, not a credential or integrity hash, and any other algorithm breaks the handshake. |
| garageSocket | jssecurity:S5144; tools/onlyoffice_integration/garage_tls.cjs | The fixture gateway forwards only to the fixed local Garage Unix socket. It accepts only allowlisted methods and fixture Host values, and `gatewayPath` accepts only a bounded origin-relative path, so a request cannot select a peer. |
| loopbackStorageTls | python:S5332; tools/onlyoffice_integration/loopback_storage_proxy.py | The storage adapter listens only on 127.0.0.1 inside an explicitly owned fixture container, and wraps every connection in TLS 1.2 or later with the fixture certificate. |
| clusterServiceHttp | python:S5332; tools/cloudbeaver/kube_support.py | The regression probes call `cluster.local` service names inside a disposable test cluster, whose services have no TLS. Production traffic reaches CloudBeaver through the TLS ingress, which these probes do not stand in for. |
| syncContractFixture | secrets:S2068; src/applications/medilab-sync/src-tauri/src/contract.rs | The flagged value is the synthetic `fixture` password of a unit-test sign-in body that checks OpenAPI contract validation. It authenticates nothing. |
| composeEnvRewrite | pythonsecurity:S2083; tools/scripts/compose_env.py | `dev:setup` rewrites the `.env` beside the Compose file and keeps its other lines. The path is the fixed `ENV_FILE`, found from the script and never taken from input or file content; the flagged source is that same file's own lines. Values from the selection marker are written only through `_env_line`, which refuses a key outside `[A-Z][A-Z0-9_]*` and a value with CR, LF or NUL, so marker content cannot add or alter lines. |

## Accepted risks

A real finding the owner agreed to keep is marked Accepted in SonarQube with its reason, not excluded, so the rule keeps reporting new occurrences in the same file.

| Rule and file | Approval | Reason, implications and compensating controls |
| --- | --- | --- |
| java:S4790; infra/cluster/cloudbeaver/bootstrap/Authentication.java | Owner (KietPham-VN), 2026-11-24 | CloudBeaver 26.2.2's local login requires the uppercase MD5 of the password, and no compatible secure alternative exists. See [Accepted risk](cloudbeaver-security-review.md#accepted-risk). |
| python:S4790; tools/cloudbeaver/runtime.py | Owner (KietPham-VN), 2026-11-24 | The regression client speaks the same required protocol against disposable containers with credentials generated for each run. See [Accepted risk](cloudbeaver-security-review.md#accepted-risk). |

## Related documents

- [Reports index](readme.md)
- [Local setup security review](local-setup-security-review.md)
- [CloudBeaver security and peer review](cloudbeaver-security-review.md)
