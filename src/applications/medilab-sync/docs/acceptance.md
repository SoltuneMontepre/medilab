# Sync acceptance review

This maps every description and acceptance item in [#206](https://github.com/SoltuneMontepre/medilab/issues/206), in issue order, to client code, tests and remaining dependencies. D/A labels below are review references, not new product requirements. The approved migration decision is explicit rebinding: there is no verified mapping of old server folder IDs. No production signing-key scenario has been chosen.

Statuses distinguish implemented and tested, implemented but not fully tested, not implemented, blocked by another workstream, and requires an owner decision. An installed-state fixture or passing unit suite is not an installed-release migration rehearsal.

## Description criteria

| Ref | Criterion | Status | Implementation and evidence / remaining dependency |
| --- | --- | --- | --- |
| D1 | New API base, including updater address | Implemented and tested | `api.rs`, `server_url.rs`, `updater.rs`; all mock/live device traffic validates shared operation paths; updater URL tests include platform/version and base paths. The server updater endpoint is absent; see A1. |
| D2 | DTO fields, rules, roles and platform mapping | Implemented and tested | `wire.rs` and `api.rs` adapters; schema-checked mock/live sign-in, folders/rules, members, uploads, versions/history, restore and download. Local paths never enter folder creation bodies. |
| D3 | Bearer only, no device-ID header, versioned User-Agent on every request | Implemented and tested | Metadata contract checks; updater fixture checks; storage mock checks versioned User-Agent and absence of device credentials on PUT/GET. Storage clients gained their missing User-Agent in this completion pass. |
| D4 | Status/code errors, transient retries, invalid-key sign-out | Implemented and tested | `error.rs`, `api.rs`, `api_auth_tests.rs`, session/retry tests. Live unissued/revoked keys are refused; translated messages do not drive decisions. 429/503 backoff and Retry-After are tested separately from job retry limits. |
| D5 | Durable prepare idempotency, multipart, finalization/polling and terminal outcomes | Implemented and tested | `storage.rs`, upload/dispatcher/recovery tests and actual Odoo/Garage integrity tests. Live dropped successful prepare response plus database reopen reuses the key/upload and creates one version; see A3. |
| D6 | OS keyring identity, locked store, opt-in file fallback | Implemented and tested | `auth.rs` and authentication/session tests cover lock classification, no fallback on lock, opt-in policy, atomic private files and symlink-safe writes. Native OS-store/platform pilot is still required under A2. |
| D7-A-client | Existing trust verifies updates and preserves local state | Implemented and tested | `updater_migration_tests.rs` runs actual Tauri check/download/signature/install against a temporary executable and legacy-schema SQLite fixture using ephemeral test keys. Wrong-key/tampered payloads preserve both. This is not A4's original installed binary. |
| D7-A-server | Old updater route serves the existing-key artifact; other legacy routes return 410 | Blocked by another workstream | Server compatibility/updater routes and signed release artifacts do not exist on this branch. Actual HTTP probes return 404. Precise route/auth/status/body/test/file handoff: [migration handoff](migration-handoff.md). |
| D7-B-client | Visible 410, safe download action, preservation on reinstall | Implemented but not fully tested | New client shows a server-scoped refusal in EN/VI, holds jobs without exhausting retries, opens a validated link on click, and reports launcher errors. HTTP refusal/render/safety tests and legacy-schema reopen/live reauthentication/rebind/upload pass. Original legacy UI and native uninstall/reinstall retention are unverified. |
| D7-B-server | All legacy routes including updater return 410 plus download link | Blocked by another workstream | No compatibility catch-all or approved deployed installer location. `error.download_url` is the proposed structured field; it needs server/release agreement. Immutable legacy updater error suppression cannot be fixed in new client code. |
| D7-shared | Old key refused; retain files, queue, identity; explicit rebinding; resume safely | Implemented and tested | `migration_tests.rs`, `sign_in_state.rs`, storage/ownership tests. Legacy-schema fixtures preserve rows/bytes/UID, block claims until binding, clear obsolete sessions, roll back an injected interruption, resume after reopen, and retain valid new bindings on same-account reauthentication. Equivalent normalized server URLs do not discard bindings. |
| D7-choice | Select production scenario and identify installed releases | Requires an owner decision | Existing key availability, installation inventory/package types, installer availability and uninstall retention are not verified. No private production key was read, created, replaced or rotated. |
| D8 | Mock checks actual OpenAPI requests/responses with locked dependencies | Implemented and tested | `contract.rs` loads the actual YAML with `include_str!`; `Cargo.lock` pins YAML/JSON Schema tooling. Checks cover path/body/query/header requirements, response status/body/media type and present optional headers. Mutated schema requirements fail validation. |

## Acceptance criteria

| Ref | Issue acceptance criterion | Status | Evidence / gap |
| --- | --- | --- | --- |
| A1 | Every application call passes shared-contract mock and running Odoo tests | Blocked by another workstream | Documented device operations pass mock and live Odoo checks. Updater has neither an OpenAPI operation nor a live server route; it cannot honestly be counted as passing the shared contract. Presigned storage uses the storage protocol, separately exercised against Garage. |
| A2 | Sign-in stores key, never password; locked store unlock/retry keeps session | Implemented but not fully tested | Credential policy, crash recovery, session and UI regressions pass; actual Odoo authenticates fresh/invalid/revoked keys. A native isolated Secret Service/Credential Manager/Keychain and installed-platform UI rehearsal was not run. No host production credential store was used for tests. |
| A3 | Lost upload answer retry creates one version | Implemented and tested | Mock lost prepare/finalize and restart tests; live `live_lost_prepare_reply_and_restart_create_one_upload_and_one_version` forwards prepare to Odoo, drops its successful reply, reopens SQLite, then proves equal persisted key/upload IDs and one version. |
| A4 | Original installed release updates automatically, preserves state, signs in and syncs | Blocked by another workstream | Real Tauri test-signed temporary executable installation, unchanged legacy database bytes, migration/rebind/live upload are verified separately. Original installer, compatibility server, release artifacts and native package lifecycle evidence are missing. These tests do not satisfy original-release acceptance. |
| A5 | Original installed release shows legacy 410/link on every call; reinstall signs in/syncs and preserves data | Blocked by another workstream | New client refusal handling and a live legacy-state reauthentication/rebind/upload fixture pass. Old binaries, all-path legacy server responses and native uninstaller retention are missing. Baseline updater suppresses errors; an owner must resolve that immutable-client limitation before this criterion can pass. |
| A6 | `task test:apps` passes in `ci-sync-app` | Not implemented | The command passes locally with actual Cargo and Mobile tests. Workflow runs separate Bun/Cargo steps, not literal `task test:apps`; no hosted CI result is claimed. CI-owner handoff specifies the required application job and aggregation. |
| A7a | CI checks the same OpenAPI document | Implemented and tested | Rust tests use the repository YAML directly; no copied mock schema. Existing backend CI invokes that suite. Hosted run remains unverified. |
| A7b | OpenAPI-only changes rerun Sync CI | Not implemented | Current relevant-change filter omits YAML. [Isolated proposed patch](../proposals/ci-sync-contract.patch) applies cleanly; filter evaluation proves current=false/proposed=true. Workflow itself is untouched. |

## Rules and desktop browser handoff

| Ref | Rule / #230 Sync requirement | Status | Evidence / gap |
| --- | --- | --- | --- |
| R1 | Local folder paths stay on the computer | Implemented and tested | Contract rejects undeclared request fields; create/bind payload mapping sends names and remote IDs, not local paths. Local DB and file fixtures remain local. |
| R2 | Sync works without editing service | Implemented and tested | Odoo/Garage tests run with only this isolated stack's database, bucket and Odoo services. Sync uses no editor configuration. Actual page outage UX remains Agent 1/#203 scope. |
| R3 | Security and synchronization guarantees | Implemented and tested | Existing bounded concurrency, 128 MiB part budget, pause/resume, retry limits, verification, binding ownership and crash recovery suites remain passing; credential/query redaction and safe URL tests pass. This is not a security/staging certification. |
| SYNC-OPEN | Default browser via existing opener plugin | Implemented and tested | Shared `browser::open_editor` invokes `app.opener().open_url(url, None)`. Linux subprocess exercises that real plugin with isolated `xdg-open`, checks the sole URL argument, missing launcher and retry. No browser is hardcoded. |
| SYNC-URL | HTTP(S), positive ID, approved base path, no secrets | Implemented and tested | Rust URL/unsafe-origin/ID tests; TypeScript safe-integer tests. No key, JWT, redirect query or fragment is placed in the editor URL. |
| SYNC-ELIGIBILITY | Exclude raw/report/unsupported Office actions | Implemented and tested | `officeFiles.test.ts`: docx/xlsx/pptx working/result/uncategorized permitted, raw/report/unknown/non-Office excluded. Server remains the authorization authority. |
| SYNC-CLEANUP | Remove obsolete embedded editor after replacing callers | Implemented and tested | Embedded editor, Office session DTOs and legacy editor API call were removed in existing #230 commits; TypeScript build and complete app tests pass. |
| PG-AUTH | Safe browser login and return | Blocked by another workstream | Agent 1's reviewed source uses authenticated HTML route and sanitized relative return, with injected-target/device-key tests. That page is absent from this branch's live stack. Cross-branch graphical login/return and external base-path ingress handling remain integration gates. |
| PG-UI | Actual editor load/save, coediting and outage | Blocked by another workstream | #230/#171/#203 own actual page, pinned Document Server and deployment evidence. OS launcher success is not evidence of editor load or save. |

## Verification evidence

Branch baseline `01856e9` was rerun before changes: **201 Rust tests passed, 13 ignored, no failures**. The completion pass adds client refusal handling, storage User-Agent coverage, canonical server identity preservation, stronger contract drift checks, legacy-schema/interruption/live-loss fixtures and Linux native-opener coverage. No unrelated server or workflow implementation was changed.

Final local verification:

| Check | Result |
| --- | --- |
| TypeScript typecheck + Vite build (`bun run build`) | Passed |
| Sync Bun tests | 53 passed, 0 failed |
| Actual Rust suite via `task test:apps` | 212 passed, 0 failed, 16 ignored by default |
| Mobile tests via `task test:apps` | 4 passed in 3 suites |
| Strict Clippy, all targets/features, warnings denied | Passed |
| Rust format and production debug build with locked dependencies | Passed |
| Device OpenAPI validation and compatibility against `origin/main` | Passed; no contract changes |
| Live device API authentication/members/history/restore/conflict/revocation | Passed separately against isolated Odoo/Garage |
| Live 40 MiB multipart/small-file/mixed-content integrity | Passed separately |
| Live reopened legacy-schema reauthentication/rebinding/upload | Passed separately |
| Live dropped prepare answer + database reopen + one upload/version | Passed separately |
| Test-key Tauri installation/wrong-key/tampered-payload checks | Passed in default Rust suite; no production keys |
| Linux opener launch/missing-launcher/retry | Passed in default Rust suite; its ignored subprocess worker is explicitly executed by the parent |
| CI proposal application/filter checks and diff whitespace | Passed |

Default ignored tests include environment-dependent benchmarks, workload/process-kill suites and live fixtures. The four live cases listed above were explicitly run; do not interpret the default ignored count as either their execution or success. Windows/macOS builds and native installers, a graphical desktop pilot, original installed-release migration and hosted CI were not run.

The isolated integration stack uses database `medilab_206`, Odoo port 22069, PostgreSQL port 22432 and Garage ports 22900/22903. Each fixture creates unique server folders/devices and temporary local directories. No other worktree/database/port or production data was used.

## Recommendation

The implemented desktop behavior is ready for integration review. Keep #206 open: A1, A4, A5, A6 and A7b still require server/release/CI work, A2 needs native platform evidence, and the production scenario remains undecided. The Sync portion of #230 has native launcher evidence; its authenticated browser/editor acceptance remains dependent on Agent 1 and #203. The precise handoff is reviewable without expanding this branch into Odoo or infrastructure ownership.

## Related documents

- [Migration integration handoff](migration-handoff.md)
- [Maintenance and commands](maintenance.md)
- [Client contract](contract.md)
