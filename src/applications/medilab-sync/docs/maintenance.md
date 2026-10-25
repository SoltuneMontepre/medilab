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

The Rust test transport validates metadata requests and responses against `sol_laboratory/api/openapi.yaml`, including operation paths, body/query/header schemas, required response headers and response statuses. This applies to the mock and actual API tests. Locked Rust test dependencies supply YAML and JSON Schema validation. The mock's small multipart size accelerates concurrency tests; actual API tests exercise the server's part size and asynchronous verification.

Tests cover durable preparation keys after lost responses and restart, lost finalize replies, upload integrity, concurrent parts, buffer budgets, pause/resume, recovery, binding ownership races, credential-store locking, private fallback files, installed-state preservation and browser handoff.

Actual API tests are separate and ignored by default. Point them only at a disposable database and bucket with another authorized tester available for the membership fixture:

```sh
export MEDILAB_E2E_URL=http://localhost:22069
export MEDILAB_E2E_LOGIN=demo.tester
export MEDILAB_E2E_PASSWORD=<local-demo-password>
cargo test --manifest-path src-tauri/Cargo.toml api_live_tests -- --ignored --nocapture
cargo test --manifest-path src-tauri/Cargo.toml sync::live_tests::live_upload_integrity -- --ignored --exact --nocapture
```

The actual API fixture creates its own folders and device UIDs. It covers sign-in, current-device validation, membership, rules, empty content, repeated preparation/finalization, history, restore, download, case-variant conflict paths, changes, revocation and repeated sign-out. The integrity test exercises a small file, a 40 MiB multipart file and a changed file rejected before finalization. Benchmark and process-kill tests need their own budgets and environment; do not equate fixture-only evidence with production validation.

## Installed release migration

Back up and verify the application's data directory before a pilot. Preserve the identifier `com.medilab.filesync`, `sync.sqlite`, installation UID and OS credential-store service/account. Do not remove application data during reinstallation.

After signing in again, migrated folders remain visible as not bound. Choose an existing server folder and the same local directory to resume the preserved queue. The client does not infer folder identity from a reused numeric ID. Review existing local/server differences through the normal conflict flow.

The release owner must verify whether the current updater signing key exists, identify installed versions and choose the documented signed-update or reinstall scenario. Never generate, replace or rotate production keys as a migration shortcut. The old-address compatibility manifests/refusals, approved installer location and a real installed-client rehearsal are server/release dependencies outside the desktop's code. See the [contract](contract.md#installed-clients-and-updates).

The new updater path is `/medilab/api/v1/updates/<target>/<arch>/<version>`. It requires a server endpoint and contract. CI also needs to trigger the Sync contract suite when only the shared OpenAPI document changes; that workflow is maintained outside this application's owned directory.

## Browser pilot

Verify the default-browser action on Linux and Windows, including launch failure and a second attempt. Check login/return and the actual editor page supplied by the server. Confirm that raw/report/non-Office files offer no edit action. An opener unit test does not prove the browser loaded the editor or saved a document. Real pinned Document Server coediting, outage, long-session and staging checks remain shared integration gates.

## Related documents

- [Contract](contract.md)
- [Database](database.md)
- [Technician guide](technician.md)
- [Pilot](pilot.md)
