# Local setup security review

The local setup is developer tooling for the authorized OS user, selected checkout and local Docker/Podman engine. It is not exposed as a multi-user command service. An HTTP client must not select a host command, filesystem path, storage bucket or proxy destination. Private state must resist another local principal that can write an ancestor directory. OS administrators remain privileged independently of these tools.

## Sonar dispositions

The owner authorized ignoring confirmed false positives. `sonar-project.properties` scopes each exclusion to one rule and one file. Other rules continue to scan those files. These exclusions do not approve arbitrary endpoints, untrusted command callers or weakened ownership checks. Review them again if a boundary below changes.

| Exclusion | Rule and file | Reason and required controls |
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

## Private state integrity

The shared guard validates the managed chain from `ROOT/.local` before reads, writes or creation, including bootstrap markers, archives and switch journals. It rejects links, unexpected types, untrusted ownership and untrusted ancestor writers. It does not reject unrelated OS ancestors such as the system temporary directory.

On POSIX the chain must be current-user-owned and must not grant group/other write. On Windows the ancestor check rejects mutation grants to untrusted trustees. Current user, SYSTEM and BUILTIN\Administrators are already privileged for ancestor integrity. This does not change an ACL. Private leaves still require protected current-user/SYSTEM-only access; an Administrators grant is not accepted on a secret leaf.

Only directories created by the current operation receive protection. Existing unsafe directories fail without being repaired, adopted or deleted. Same-user or administrator interference is outside this local CLI boundary.

Marker and Compose environment writers use exclusive temporary creation, flush/fsync, private protection and atomic publication. Switch-journal publication remains exclusive. Cleanup removes only the current operation's temporary file. Foreign preexisting `.tmp` files or links are neither followed nor deleted.

## Garage ownership semantics

[AWS documents ExpectedBucketOwner](https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html) as an AWS account-ID check; a mismatch should return HTTP 403. The pinned [Garage compatibility reference](https://github.com/deuxfleurs-org/garage/blob/v2.4.1/doc/book/reference-manual/s3-compatibility.md) notes incomplete x-amz header support. Compatibility documentation alone does not prove behavior.

The recorded read-only provider probe used label-verified Garage v2.4.1, image digest `sha256:9c96caa2612d3411acc5b0e6701fb238dbfba33e533a6d7d3d811a4b12d0d020`, and an existing database marker:

| Probe | Recorded result |
| --- | --- |
| HeadBucket with ExpectedBucketOwner 000000000000 / 111111111111 | 200 / 200 |
| HeadObject with the same two different owner values | 200 / 200 |
| HeadObject with an invalid signing secret | 403 |

The probe created or modified no bucket, object, key or permission. It establishes that these operations on the pinned provider ignore the AWS expected-owner contract while rejecting a bad signature. It does not establish ownership of an arbitrary AWS bucket or justify generalizing the verifier to arbitrary storage endpoints. The verifier must remain bound to the selected local Garage and expected bucket.

## Regression evidence

`tools/onlyoffice/test_verifier.py` rejects foreign bucket/origin inputs before client creation, refuses malformed cleanup identities, preserves unrelated objects, cleans the disposable key after conversion failures, and distinguishes access errors or retained objects from successful cleanup.

`tools/onlyoffice/test_proxy.py` exercises encoded traversal, foreign/duplicate Host, forbidden public commands, redirects and WebSocket handshake validation. The Docker network proof additionally checks allowed routes, backend and metadata denial, positive controls, wrong CA/SAN and bidirectional WebSocket traffic.

`tools/scripts/test_local_compose.py` checks project/file override rejection before engine calls and intentional run/exec argument preservation. State, native ACL and private writer suites cover malformed identities, foreign configuration paths, unsafe ancestors and temporary-file links. Native Windows ACL execution remains a separate hosted check.

Run the focused suites from the repository root using the locked core environment:

```text
uv run --locked --no-build --project src/core python -m unittest discover -s tools/scripts -p 'test_onlyoffice*.py'
uv run --locked --no-build --project src/core python -m unittest discover -s tools/scripts -p test_local_compose.py
uv run --locked --no-build --project src/core python -m unittest discover -s tools/scripts -p test_local_private_paths.py
uv run --locked --no-build --project src/core python -m unittest discover -s tools/scripts -p test_private_state_writers.py
uv run --locked --no-build --project src/core python -m unittest discover -s tools/onlyoffice -p 'test_*.py'
```

Passing local tests does not establish a hosted Sonar quality-gate result or native Windows acceptance. Repository exclusions take effect when Sonar analyzes the change.

## Related documents

- [ONLYOFFICE infrastructure](../infrastructure/onlyoffice.md)
- [Local setup](../workflows/setting-up.md)
- [Windows acceptance](../workflows/windows-acceptance.md)
- [Security permissions](../security/readme.md)
