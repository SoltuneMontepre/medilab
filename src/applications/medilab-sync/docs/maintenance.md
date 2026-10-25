# MediLab Sync maintenance

## Development

Use the [repository setup workflow](../../../../docs/workflows/setting-up.md) and an isolated stack as described in [README](../../../../README.md#a-second-stack-from-a-worktree). Sync uses the laboratory files API of `sol_laboratory`; Document Server is optional for file synchronization. Set the server address in the application or at build time with `MEDILAB_SYNC_ODOO_URL`. Production uses HTTPS.

The person needs the laboratory files permission and membership of the folders they bind. A sample's visibility restrictions still apply. Use local demo credentials only in an isolated test database. The development plaintext credential fallback requires an explicit opt-in and is not a production credential store.

## Verification

From `src/applications/medilab-sync`:

```sh
bun install --frozen-lockfile --ignore-scripts
bun run build
bun test
cargo fmt --check --manifest-path src-tauri/Cargo.toml
cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --all-features -- -D warnings
cargo test --locked --manifest-path src-tauri/Cargo.toml
```

From the repository root, run `task test:apps` and `task test:openapi`. Rust requires the platform Tauri development libraries; a skipped Rust invocation is not a passing Rust test result.

The Rust test transport validates metadata requests and responses against `sol_laboratory/api/openapi.yaml`, including path parameters, required body/query/header schemas, optional response headers when present, required response headers, JSON media types and response statuses. This applies to the mock and actual API tests. Drift tests mutate the shared document in memory to prove that changes affect validation. Locked Rust test dependencies supply YAML and JSON Schema validation. The mock's small multipart size accelerates concurrency tests; actual API tests exercise the server's part size and asynchronous verification.

Tests cover durable preparation keys after lost responses and restart, lost finalize replies, upload integrity, concurrent parts, buffer budgets, pause/resume, recovery, binding ownership races, credential-store locking, private fallback files, installed-state preservation and browser handoff.

Actual API tests are separate and ignored by default. Point them only at a disposable database and bucket with another authorized tester available for the membership fixture:

```sh
export MEDILAB_E2E_URL=http://localhost:22069
export MEDILAB_E2E_LOGIN=demo.tester
export MEDILAB_E2E_PASSWORD=<local-demo-password>
cargo test --manifest-path src-tauri/Cargo.toml api_live_tests -- --ignored --nocapture
cargo test --manifest-path src-tauri/Cargo.toml sync::live_tests::live_upload_integrity -- --ignored --exact --nocapture
cargo test --locked --manifest-path src-tauri/Cargo.toml migration_tests::live_ -- --ignored --nocapture
```

The actual API fixture creates its own folders and device UIDs. It covers sign-in, current-device validation, membership, rules, empty content, repeated preparation/finalization, history, restore, download, case-variant conflict paths, changes, revocation and repeated sign-out. The integrity test exercises a small file, a 40 MiB multipart file and a changed file rejected before finalization. Migration fixtures open the legacy SQLite schema, reauthenticate, require rebinding and upload preserved bytes. A live proxy drops a successful prepare answer; after SQLite reopen, the persisted key reuses one server upload and adds one version. Benchmark and process-kill tests need their own budgets and environment; do not equate fixture-only evidence with production validation.

## Installed release migration

Back up and verify the application's data directory before a pilot. Preserve the identifier `com.medilab.filesync`, `sync.sqlite`, installation UID and OS credential-store service/account. Do not remove application data during reinstallation.

After signing in again, migrated folders remain visible as not bound. Choose an existing server folder and the same local directory to resume the preserved queue. The client does not infer folder identity from a reused numeric ID. Review existing local/server differences through the normal conflict flow.

The release owner must verify whether the current updater signing key exists, identify installed versions and choose the documented signed-update or reinstall scenario. Never generate, replace or rotate production keys as a migration shortcut. The old-address compatibility manifests/refusals, approved installer location and a real installed-client rehearsal are server/release dependencies outside the desktop's code. See the [contract](contract.md#installed-clients-and-updates).

The new updater path is `/medilab/api/v1/updates/<target>/<arch>/<version>`. It requires a server endpoint and contract. The Sync CI relevant-change filter includes the shared OpenAPI document, and its root application job runs `task test:apps` with Cargo present. Hosted execution remains a separate acceptance gate.

`updater_migration_tests` generates ephemeral test keys in memory, serves signed fixture bytes and runs Tauri's actual verifier/installer against an isolated Linux executable. It checks successful replacement and data retention, plus wrong-key/tampered-byte refusal before replacement. It does not invoke native DEB/RPM/NSIS/DMG uninstallers or exercise an original installed release. Never supply a production private key to this suite. See the [acceptance review](acceptance.md) and [server/release/CI handoff](migration-handoff.md).

## Browser pilot

Verify the default-browser action on Linux and Windows, including launch failure and a second attempt. Check login/return and the actual editor page supplied by the server. Confirm that raw/report/non-Office files offer no edit action. An opener unit test does not prove the browser loaded the editor or saved a document. Real pinned Document Server coediting, outage, long-session and staging checks remain shared integration gates.

The Linux launcher regression invokes the actual Tauri opener plugin in a subprocess with an isolated `xdg-open` fixture. It checks the sole URL argument, missing-launcher error and retry without changing the host's default browser. The ignored worker is run by that parent test; it is not an unexecuted launcher gate.

## Related documents

- [Contract](contract.md)
- [Database](database.md)
- [Technician guide](technician.md)
- [Pilot](pilot.md)
