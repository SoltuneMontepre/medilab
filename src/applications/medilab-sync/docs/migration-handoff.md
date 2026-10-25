# Sync migration integration handoff

## Server ownership

The desktop owns its new API client, durable data migration, credential handling, updater address and refusal presentation. It cannot add an endpoint to a deployed Odoo server, sign a release with an unavailable private key, change an installed binary, or choose the production migration scenario.

The branch contains no `/api/sync/v1` compatibility controller or `/medilab/api/v1/updates` controller. The device OpenAPI document contains no updater operation. Current Odoo therefore returns ordinary 404 responses for these missing routes. The compatibility boundary must be implemented by the server workstream before either installed-release scenario is accepted.

## Routes and proposed contracts

Paths below are relative to the approved installation base path. Compatibility responses must work without a browser cookie or a valid old device key, including requests carrying invalid old credentials. Do not authenticate an old key as a new device or accept `X-Sync-Device-Id` as authority. Never echo a request's authorization, password, local path or query into a response or log.

| Route | Existing key available | Existing key unavailable |
| --- | --- | --- |
| `GET /api/sync/v1/updates/{target}/{arch}/{version}` | Tauri manifest referencing an artifact signed with the existing trusted key; 204 with an empty body when no eligible update exists | 410 refusal below |
| `/api/sync/v1` and every other descendant, including unknown paths and mutating methods | 410 refusal | 410 refusal |
| `GET /medilab/api/v1/updates/{target}/{arch}/{version}` | Manifest using the new client's configured trust; 204 when no eligible update exists | Manifest using the separately authorized new release's trust; 204 when no eligible update exists |
| New device API routes | Existing documented Bearer contract; old/unissued keys receive 401 `invalid_key` | Same |

The catch-all must include legacy sign-in/sign-out/device/folder/file/upload/editor routes, the prefix root and a trailing slash. In the unavailable-key scenario it must also cover updater paths and methods, rather than redirecting to HTML or demanding authentication. Preserve normal status, authentication and method handling outside the legacy prefix. Do not revive the legacy upload implementation.

Proposed 410 JSON response (the issue specifies the code and link, but no structured link field):

```http
HTTP/1.1 410 Gone
Content-Type: application/json
Cache-Control: no-store

{"error":{"code":"client_update_required","message":"Install the current MediLab Sync release. Keep application data and sign in again.","download_url":"https://lims.example/download/medilab-sync"}}
```

`error.download_url` is the proposed interoperable field implemented by the desktop. The desktop displays the message as text, offers the link only after validating it, and opens it with the OS default handler only on an explicit click. It accepts HTTPS, or loopback HTTP for isolated tests, and excludes userinfo, query strings, fragments, control characters and unsafe path syntax. An absent/unsafe link yields administrator guidance. Supply a stable public download page rather than a credentialed or expiring signed URL. Neither a 410 nor a download click installs anything or changes updater trust.

A 200 dynamic Tauri manifest example is:

```json
{
  "version": "0.2.0",
  "notes": "Laboratory files API migration",
  "url": "https://lims.example/download/medilab-sync-update.tar.gz",
  "signature": "<base64 encoded minisign signature text for these exact artifact bytes>"
}
```

The updater signature authenticates the artifact bytes; do not claim that an unsigned JSON manifest itself establishes trust. Select an actually supported artifact for each installed package/platform/architecture and version. Reject invalid target/architecture/version/channel values; do not interpolate them into filesystem paths. Document the optional non-stable `channel` query, no-update behavior, JSON media type, response headers and failure statuses in an OpenAPI contract before enabling request/response checking for updater calls. The desktop sends a versioned User-Agent and no device authorization on updater checks. It observes a typed 410 in a separate request before invoking Tauri's normal manifest/signature path; ordinary successful checks consequently make two manifest requests.

A new device request with an invalid old key remains the existing contract:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json

{"error":{"code":"invalid_key","message":"Sign in again."}}
```

Do not add `client_update_required` to the new device API implicitly. If the server intends that status there too, explicitly version/update its OpenAPI response declarations and tests. The desktop recognizes the typed refusal defensively, but contract validation correctly rejects undocumented responses.

## Affected server files

The server owner should add dedicated controllers such as `controllers/laboratory_sync_compatibility.py` and `controllers/laboratory_api_updates.py`, importing them in `controllers/__init__.py`. Review the interaction with `models/laboratory_files/ir_http.py` and `services/laboratory_api.py`: they currently wrap errors only for the new API prefix, and the route helper requires a declared OpenAPI operation. Keep compatibility routing and public updater authentication separate from the device-key route helper unless it is deliberately extended with a documented public operation.

Add the updater operation/response schemas to `api/openapi.yaml`, or a separately indexed updater contract if the API owner chooses that boundary. Keep legacy refusal schemas separately documented if they are not device operations. Relevant existing error/authentication constants live in `constants/laboratory_api.py` and `constants/laboratory_files.py`; old-key validation is owned by `models/laboratory_files/laboratory_device.py` and the sign-in/device controllers. Reuse those checks rather than migrating old credentials by numeric ID.

Required server tests:

1. Normal HTTP requests at the legacy root, unknown descendants, updater route, each representative legacy operation and mutating/OPTIONS methods. Assert the exact 410 code/link/media type/no-store behavior without cookies, with malformed/old Bearer keys and with legacy headers. Assert no model mutation and no credential echo.
2. Scenario A manifest selection, 204 no-update, platform/architecture/version/channel input refusal, artifact availability and exact signature bytes. Use an ephemeral test key and an isolated artifact server. Ensure the legacy updater route takes precedence over the catch-all.
3. Scenario B updater and other legacy paths all return the same safe manual-download contract. Links must not be derived from untrusted Host/query values. Verify wrong/new keys cannot update an old trusted installation.
4. New device API still refuses unissued old keys with 401 `invalid_key`, and fresh sign-in/revocation works. New routes outside the compatibility boundary retain their existing errors.
5. Actual published legacy installers on supported OS/package types, upgraded or uninstalled/reinstalled against this server, with real installation/data-directory and isolated credential-store fixtures. Verify data, queue, UID, authentication and upload bytes after explicit rebinding. The test-signed executable and SQLite fixtures in this branch do not replace this gate.

## Release ownership and unresolved evidence

No production scenario has been selected and no production signing key has been inspected or changed. The owner must identify installed versions/package types and verify existing key availability without exposing it. GitHub's releases list was empty at review time; no original published installer was available for an installed-release rehearsal.

`.github/workflows/cd.sync-app.yml` currently builds DEB/RPM, NSIS and DMG packages but does not apply `tauri.updater.conf.json`, configure signing or collect updater signatures/artifacts. The release owner must prepare appropriate signed artifacts, metadata and an approved public download address. Do not generate or substitute a production key to satisfy a test.

The unchanged legacy updater logs errors and returns `None`; it has no actionable 410/download UI. A server JSON response cannot retrofit that UI into immutable installations. Scenario B's requirement that the old application itself shows a link therefore needs identified legacy binaries proving support, or an owner-approved change to that acceptance path (for example an independently delivered bridge/manual notification). The new client implements visible refusal handling, but cannot establish what unavailable old binaries do.

The approved data contract requires explicit rebinding because there is no verified mapping of old folder IDs. Migration preserves SQLite rows, queued work, local paths/files, installation identity and the credential-store address. It quarantines old remote IDs and sessions transactionally. Reauthentication to the same new server/account preserves already migrated, valid bindings. An uninstaller must retain application data; deleting a data directory cannot be repaired by reinstalling client code. Native installer retention and real OS-store behavior need platform rehearsal.

## CI ownership

[Proposed CI patch](../proposals/ci-sync-contract.patch) changes only `ci.sync-app.yml`: it adds the shared OpenAPI document to the relevant-change filter and locks Rust test resolution. It is deliberately not applied to the workflow. `git apply --check` verifies it against this branch.

Today a PR changing only `src/core/modules/sol_laboratory/api/openapi.yaml` starts change detection, which reports `relevant=false`; Sync lint/build/test jobs skip. The proposed filter fixes that. `include_str!` loads the actual shared YAML, so the Rust suite rebuilds and validates actual mock/live traffic rather than a copied schema. Negative tests mutate request, path, query, response-header and response-body requirements and demonstrate rejection.

The workflow separately runs Bun and Rust tests; it does not run the literal `task test:apps` command, which also runs Mobile tests. The CI owner must add a root-working-directory application test job/step with Bun, Rust, Linux Tauri libraries, built/placeholder frontend assets and Task (the repository already uses `arduino/setup-task@v3`). Run `task test:apps` with Cargo present and include it in the required test aggregation. Do not count the script's Cargo-not-found skip as a backend pass. Hosted execution and required-check configuration are still unverified; this branch neither edits unrelated workflows nor claims hosted CI success.

## Browser page integration

The desktop matches Agent 1's `GET /medilab/laboratory-files/<file_id>/edit`, using the configured HTTP(S) base path and default opener. It sends no Bearer key, editor JWT or redirect query. Linux tests invoke the real opener plugin with an isolated `xdg-open` fixture and check missing-launcher errors/retry; they do not prove a graphical browser or editor loaded.

Agent 1's controller uses `type='http'`, `auth='user'`, `readonly=False`. Its `ir_http_editor.py` builds a relative login/identity return using only the editor path and discards caller queries; its tests reject injected redirect targets and device keys. This source review was against local page commit `5a7e48f0afa7c64cca245a844a1408c7480b25cc`, without changing its tree. The page is absent from this Sync branch's running Odoo stack. Full browser login/return, actual Office saves and outage behavior remain #230/#203 tests.

For installations under an external base path, desktop URL construction is covered. The page currently emits root-relative login/assets paths; the server/ingress owner must verify prefix rewriting or SCRIPT_NAME handling end to end. No desktop URL rewrite or credential injection should compensate for an unverified server deployment configuration.

## Related documents

- [Contract](contract.md)
- [Maintenance](maintenance.md)
- [Acceptance review](acceptance.md)
