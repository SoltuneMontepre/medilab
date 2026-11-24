# Local setup security review

The local setup is developer tooling for the authorized OS user, selected checkout and local Docker/Podman engine. It is not exposed as a multi-user command service. An HTTP client must not select a host command, filesystem path, storage bucket or proxy destination. Private state must resist another local principal that can write an ancestor directory. OS administrators remain privileged independently of these tools.

## Sonar dispositions

The Sonar exclusions of these tools and their required controls are listed in [Sonar dispositions](sonar-dispositions.md).

## Private state integrity

The shared guard validates the managed chain from `ROOT/.local` before reads, writes or creation, including bootstrap markers, archives and switch journals. It rejects links, unexpected types, untrusted ownership and untrusted ancestor writers. It does not reject unrelated OS ancestors such as the system temporary directory.

On POSIX the chain must be current-user-owned and must not grant group/other write. On Windows the ancestor check rejects mutation grants to untrusted trustees. Current user, SYSTEM and BUILTIN\Administrators are already privileged for ancestor integrity. Private leaves still require protected current-user/SYSTEM-only access; an Administrators grant is not accepted on a secret leaf.

Directories created by the current operation receive protection. On Windows an existing directory in the chain is repaired when it is owned by the current user, or by BUILTIN\Administrators under an elevated token, is not a link or junction, and every untrusted writer on it is inherited, such as a drive-wide `Authenticated Users: Modify` grant. The repair disables inheritance, grants only the current user and SYSTEM, propagates to inheriting children and prints one line per repaired directory. Every other unsafe path fails without being repaired, adopted or deleted: another owner, an explicit untrusted grant, a link or junction, or a file. POSIX modes are never repaired. Same-user or administrator interference is outside this local CLI boundary.

Windows ACLs are written with `SetAccessControl` on the item rather than `Set-Acl`, which needs `SeSecurityPrivilege` on directories that Python 3.13 creates with `mkdir(mode=0o700)`.

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
