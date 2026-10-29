# Sync acceptance review

This maps every description and acceptance item in [#206](https://github.com/SoltuneMontepre/medilab/issues/206), in issue order, to client code, tests and remaining dependencies. D/A labels below are review references, not new product requirements. The approved migration decision is explicit rebinding: there is no verified mapping of old server folder IDs. No production signing-key scenario has been chosen.

Statuses have three meanings:

- **Completed and verified**: the stated client boundary has passing local evidence; this does not imply a native release or hosted result.
- **Implemented but awaiting integration**: client implementation and local coverage exist, but the stated end-to-end/native evidence is missing.
- **Blocked by server, CI, or release dependencies**: work or evidence owned outside this client branch is missing. Owner decisions are release dependencies, not implicit approvals.

An installed-state fixture or passing unit suite is not an installed-release migration rehearsal. The Owner column names the responsible workstream; individual server/CI/release assignees must be allocated by the maintainer rather than inferred here.

## Integrated review

Preserved source client commits `29a6aa814ab76cc020a23f3dffac745da51ee9ea`, `62d2ee029b2a4025b659653aa1c4378051bbb53f` and `21e03c9bbe773ba70ebc45e6df7377eaa166e500`. Author and committer on each are `KietPham-VN <153413668+KietPham-VN@users.noreply.github.com>`. The integration also includes the approved server updater/legacy boundary and combined editor verification.

The independently executable client criteria have implementations and passing coverage: API/DTO/authentication/error handling, persistent idempotency and upload completion, credential-store policy, queue/binding preservation and recovery, updater refusal/trust handling, and default-browser handoff. Migration, updater, rollback/recovery and retention safeguards remain intact; the integrated suites exercise their shared server contracts. Native credential-store UI, original installers and the complete graphical desktop pilot remain unverified.

## Description criteria

| Ref | Criterion | Status | Owner | Implementation and evidence / remaining dependency |
| --- | --- | --- | --- | --- |
| D1 | New API base, including updater address | Completed and verified | Sync client (Agent 3) | `api.rs`, `server_url.rs`, `updater.rs`; all mock/live device traffic validates shared operation paths; updater URL tests include platform/version and base paths. The integrated public updater is implemented under its separately versioned shared contract; see A1 and the integration report. |
| D2 | DTO fields, rules, roles and platform mapping | Completed and verified | Sync client (Agent 3) | `wire.rs` and `api.rs` adapters; schema-checked mock/live sign-in, folders/rules, members, uploads, versions/history, restore and download. Local paths never enter folder creation bodies. |
| D3 | Bearer only, no device-ID header, versioned User-Agent on every request | Completed and verified | Sync client (Agent 3) | Metadata contract checks; updater fixture checks; storage mock checks versioned User-Agent and absence of device credentials on PUT/GET. Storage clients gained their missing User-Agent in this completion pass. |
| D4 | Status/code errors, transient retries, invalid-key sign-out | Completed and verified | Sync client (Agent 3) | `error.rs`, `api.rs`, `api_auth_tests.rs`, session/retry tests. Live unissued/revoked keys are refused; translated messages do not drive decisions. 429/503 backoff and Retry-After are tested separately from job retry limits. |
| D5 | Durable prepare idempotency, multipart, finalization/polling and terminal outcomes | Completed and verified | Sync client (Agent 3) | `storage.rs`, upload/dispatcher/recovery tests and actual Odoo/Garage integrity tests. Live dropped successful prepare response plus database reopen reuses the key/upload and creates one version; see A3. |
| D6 | OS keyring identity, locked store, opt-in file fallback | Completed and verified | Sync client (Agent 3) | `auth.rs` and authentication/session tests cover lock classification, no fallback on lock, opt-in policy, atomic private files and symlink-safe writes. Native OS-store/platform pilot is still required under A2. |
| D7-A-client | Existing trust verifies updates and preserves local state | Implemented but awaiting integration | Release validation + Sync maintainer | `updater_migration_tests.rs` runs actual Tauri check/download/signature/install against a temporary executable and legacy-schema SQLite fixture using ephemeral test keys. Wrong-key/tampered payloads preserve both. This is not A4's original installed binary. |
| D7-A-server | Old updater route serves the existing-key artifact; other legacy routes return 410 | Blocked by server, CI, or release dependencies | Odoo/API + release owners | Dedicated legacy/updater controllers and the approved separate OpenAPI contract pass native HTTP and real Odoo/Tauri test-key checks. Original installed trust/artifacts and native package lifecycle remain release gates; see [migration handoff](migration-handoff.md). |
| D7-B-client | Visible 410, safe download action, preservation on reinstall | Implemented but awaiting integration | Release validation + Odoo/API | New client shows a server-scoped refusal in EN/VI, holds jobs without exhausting retries, opens a validated link on click, and reports launcher errors. HTTP refusal/render/safety tests and legacy-schema reopen/live reauthentication/rebind/upload pass. Original legacy UI and native uninstall/reinstall retention are unverified. |
| D7-B-server | All legacy routes including updater return 410 plus download link | Blocked by server, CI, or release dependencies | Odoo/API + release owners | The owner approved `error.download_url`; the integrated all-path/all-method 410 boundary passes HTTP and client checks with a safe configured fixture link. Production download publication and immutable old-client UI remain release gates. |
| D7-shared | Old key refused; retain files, queue, identity; explicit rebinding; resume safely | Completed and verified | Sync client (Agent 3) | `migration_tests.rs`, `sign_in_state.rs`, storage/ownership tests. Legacy-schema fixtures preserve rows/bytes/UID, block claims until binding, clear obsolete sessions, roll back an injected interruption, resume after reopen, and retain valid new bindings on same-account reauthentication. Equivalent normalized server URLs do not discard bindings. |
| D7-choice | Select production scenario and identify installed releases | Blocked by server, CI, or release dependencies | Product/release owner | Existing key availability, installation inventory/package types, installer availability and uninstall retention are not verified. No private production key was read, created, replaced or rotated. |
| D8 | Mock checks actual OpenAPI requests/responses with locked dependencies | Completed and verified | Sync client (Agent 3) | `contract.rs` loads the actual YAML with `include_str!`; `Cargo.lock` pins YAML/JSON Schema tooling. Checks cover path/body/query/header requirements, response status/body/media type and present optional headers. Mutated schema requirements fail validation. |

## Acceptance criteria

| Ref | Issue acceptance criterion | Status | Owner | Evidence / gap |
| --- | --- | --- | --- | --- |
| A1 | Every application call passes shared-contract mock and running Odoo tests | Completed and verified | Odoo/API owner; Sync maintainer for contract integration | Device operations and updater requests/responses use their actual separate repository OpenAPI documents. Mock/device live checks and the real Odoo/Tauri signed-artifact/wrong-key/tampered/404 fixture pass. Storage integrity is exercised against real Garage; original native release acceptance remains A4/A5. |
| A2 | Sign-in stores key, never password; locked store unlock/retry keeps session | Implemented but awaiting integration | Native release validation + Sync maintainer | Credential policy, crash recovery, session and UI regressions pass; actual Odoo authenticates fresh/invalid/revoked keys. A native isolated Secret Service/Credential Manager/Keychain and installed-platform UI rehearsal was not run. No host production credential store was used for tests. |
| A3 | Lost upload answer retry creates one version | Completed and verified | Sync client (Agent 3) | Mock lost prepare/finalize and restart tests; live `live_lost_prepare_reply_and_restart_create_one_upload_and_one_version` forwards prepare to Odoo, drops its successful reply, reopens SQLite, then proves equal persisted key/upload IDs and one version. |
| A4 | Original installed release updates automatically, preserves state, signs in and syncs | Blocked by server, CI, or release dependencies | Release validation + Odoo/API | Real Tauri test-signed temporary executable installation, unchanged legacy database bytes, migration/rebind/live upload are verified separately. Original installer, production release artifacts and native package lifecycle evidence are missing. These tests do not satisfy original-release acceptance. |
| A5 | Original installed release shows legacy 410/link on every call; reinstall signs in/syncs and preserves data | Blocked by server, CI, or release dependencies | Release validation + Odoo/API + product owner | New client refusal handling and a live legacy-state reauthentication/rebind/upload fixture pass. All-path legacy HTTP responses pass; old binaries and native uninstaller retention are missing. Baseline updater suppresses errors; an owner must resolve that immutable-client limitation before this criterion can pass. |
| A6 | `task test:apps` passes in `ci-sync-app` | Blocked by server, CI, or release dependencies | CI maintainer | The command passes locally with actual Cargo and Mobile tests. The integrated workflow runs literal `task test:apps` with Rust, Bun, Task and Linux libraries; its required test aggregation checks the result. Hosted execution remains unverified. |
| A7a | CI checks the same OpenAPI document | Implemented but awaiting integration | CI maintainer | Rust tests use the device and updater repository YAML directly, with drift-negative coverage; no copied mock schema. Existing backend CI invokes that suite. Hosted run remains unverified. |
| A7b | OpenAPI-only changes rerun Sync CI | Blocked by server, CI, or release dependencies | CI maintainer | The integrated relevant-change filter includes both shared YAML documents. Local filter validation passes; hosted scheduling against an OpenAPI-only change remains unverified. |

## Rules and desktop browser handoff

| Ref | Rule / #230 Sync requirement | Status | Owner | Evidence / gap |
| --- | --- | --- | --- | --- |
| R1 | Local folder paths stay on the computer | Completed and verified | Sync client (Agent 3) | Contract rejects undeclared request fields; create/bind payload mapping sends names and remote IDs, not local paths. Local DB and file fixtures remain local. |
| R2 | Sync works without editing service | Completed and verified | Sync client (Agent 3) | Odoo/Garage tests run with only this isolated stack's database, bucket and Odoo services. Sync uses no editor configuration. Actual page outage UX remains Agent 1/#203 scope. |
| R3 | Security and synchronization guarantees | Completed and verified | Sync client (Agent 3) | Existing bounded concurrency, 128 MiB part budget, pause/resume, retry limits, verification, binding ownership and crash recovery suites remain passing; credential/query redaction and safe URL tests pass. This is not a security/staging certification. |
| SYNC-OPEN | Default browser via existing opener plugin | Completed and verified | Sync client (Agent 3) | Shared `browser::open_editor` invokes `app.opener().open_url(url, None)`. Linux subprocess exercises that real plugin with isolated `xdg-open`, checks the sole URL argument, missing launcher and retry. No browser is hardcoded. |
| SYNC-URL | HTTP(S), positive ID, approved base path, no secrets | Completed and verified | Sync client (Agent 3) | Rust URL/unsafe-origin/ID tests; TypeScript safe-integer tests. No key, JWT, redirect query or fragment is placed in the editor URL. |
| SYNC-ELIGIBILITY | Exclude raw/report/unsupported Office actions | Completed and verified | Sync client (Agent 3) | `officeFiles.test.ts`: docx/xlsx/pptx working/result/uncategorized permitted, raw/report/unknown/non-Office excluded. Server remains the authorization authority. |
| SYNC-CLEANUP | Remove obsolete embedded editor after replacing callers | Completed and verified | Sync client (Agent 3) | Embedded editor, Office session DTOs and legacy editor API call were removed in existing #230 commits; TypeScript build and complete app tests pass. |
| PG-AUTH | Safe browser login and return | Implemented but awaiting integration | Agent 1 (#230) + deployment owner (#203) | Agent 1's reviewed source uses authenticated HTML route and sanitized relative return, with injected-target/device-key tests. The combined branch has passing native login/re-entry tests and actual browser Office coediting/save and same-save Sync observer probes. The graphical Sync pilot and external base-path ingress handling remain gates. |
| PG-UI | Actual editor load/save, coediting and outage | Blocked by server, CI, or release dependencies | Agent 1 (#230) + #171/#203 owners | #230/#171/#203 own actual page, pinned Document Server and deployment evidence. Released-page two-person DOCX/XLSX/PPTX saves, the 920-second DOCX session, actual stopped-service independence and the same-save Sync observer pass locally. Native graphical desktop and staging acceptance remain open. |

## Verification evidence

Branch baseline `01856e9` was rerun before changes: **201 Rust tests passed, 13 ignored, no failures**. The completion pass adds client refusal handling, storage User-Agent coverage, canonical server identity preservation, stronger contract drift checks, legacy-schema/interruption/live-loss fixtures and Linux native-opener coverage. No unrelated server or workflow implementation was changed.

Implementation verification for `21e03c9` (retained logs; application code is unchanged by this handoff):

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
| Integrated CI filter/syntax checks and diff whitespace | See the combined integration report; hosted execution remains unverified. |

Default ignored tests include environment-dependent benchmarks, workload/process-kill suites and live fixtures. The four live cases listed above were explicitly run; do not interpret the default ignored count as either their execution or success. Windows/macOS builds and native installers, a graphical desktop pilot, original installed-release migration and hosted CI were not run.

The isolated integration stack uses database `medilab_206`, Odoo port 22069, PostgreSQL port 22432 and Garage ports 22900/22903. Each fixture creates unique server folders/devices and temporary local directories. No other worktree/database/port or production data was used.

## Remaining-gap ownership and closure conditions

| Gap | Accountable workstream | Exact evidence needed |
| --- | --- | --- |
| Legacy compatibility routes | Release owner | Implementation and native HTTP checks pass, including unknown methods, malformed credentials and no mutation. Publish the approved production download page and rehearse actual installed binaries. |
| Updater manifests and contract | Release owner | Approved contract, current/legacy catalog selection and real Odoo/Tauri fixture checks pass. Supply verified production artifacts/trust inventory and native package lifecycle evidence. |
| Hosted CI | CI maintainer | Execute the integrated workflow against the reviewed commit, prove hosted OpenAPI-only scheduling, and obtain passing required lint/typecheck/build/contract/application checks including literal `task test:apps` with Cargo present. Local logs are insufficient. |
| Native upgrade/reinstall | Release owner + platform validation | Identify original installed binaries/package types and verify key availability; automate both supported scenarios with isolated data/OS-store fixtures and test signing keys. Prove old-key refusal, fresh sign-in, preservation of files/queue/UID, explicit rebinding, no upload while unbound, interruption/restart safety and successful sync. Verify actual installer/uninstaller retention. |
| Immutable legacy 410 UI | Product/release owner with Odoo/API | Demonstrate that identified old binaries display the download link, or explicitly approve a revised delivery/acceptance path. A server JSON change or new-client UI cannot retrofit immutable old binaries. |
| Native credential-store UI | Platform validation + Sync maintainer | Demonstrate key-only persistence, locked-store unlock/retry without session loss, no password persistence, no implicit plaintext fallback, and crash recovery in isolated native stores. Route any reproducible client defect back to the Sync maintainer. |
| #230 browser integration | Agent 1 (#230), deployment owner (#203), callback owner (#171) | Exercise Sync-to-page default-browser login/return with no device/editor credentials in the URL, external base-path handling, authorization/eligibility and launch retry. Agent 1/#171/#203 own actual editor/coediting/save/outage evidence; no server or deployment changes belong in this Sync branch. |
| Production scenario | Product/release owner | Record verified installation inventory/key availability and explicitly select the shipping scenario. Demonstrate both documented supported paths before treating issue acceptance as complete; do not substitute a production key. |

Close #206 only when every A-row is Completed and verified: the updater boundary passes its finalized mock/live contract; native credential-store evidence is recorded; original-release scenario A and B rehearsals meet A4/A5 (or the owner explicitly revises the impossible immutable-client condition); and A6/A7 have passing hosted CI evidence, including an OpenAPI-only trigger. Record the production scenario decision and preserve the approved explicit-rebinding contract. Resolve the Sync-to-page integration gate with #230; full #230 coediting/save/staging acceptance remains with its own owners and is not authorization to duplicate that work here.

## Recommendation

The implemented desktop behavior is ready for integration review. Keep #206 open: A4/A5 need original-release/native evidence; A6/A7 need hosted CI; A2 needs native credential-store evidence; production artifacts/trust inventory and the shipping scenario remain release inputs. The Sync portion of #230 has native launcher evidence; its authenticated browser/editor acceptance remains dependent on Agent 1 and #203. The approved server contract and precise release gates are recorded in the integrated report.

## Related documents

- [Migration integration handoff](migration-handoff.md)
- [Maintenance and commands](maintenance.md)
- [Client contract](contract.md)
