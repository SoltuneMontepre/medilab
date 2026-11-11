# Sync migration integration handoff

## Server contract

The integrated server implements public updater discovery and legacy refusals in dedicated native HTTP controllers. The owner approved the separate updater contract and configured `error.download_url` boundary. [Sync updates](../../../../docs/specs/sync-updates.md) defines routes, environment variables, catalog schema, version selection and trust separation; [the shared OpenAPI document](../../../core/modules/sol_laboratory/api/sync-updates.openapi.yaml) is checked by both Odoo and Rust tests.

- New updater GET/HEAD: `/medilab/api/v1/updates/{target}/{arch}/{version}`. Eligible manifests return 200, no newer release returns 204, malformed requests return 400, wrong methods return 405, and unavailable/invalid catalogs return 503.
- Legacy root and all descendants/methods return 410 `client_update_required`, with a safe configured download page. Explicit `MEDILAB_SYNC_LEGACY_UPDATER=manifest` permits only the legacy updater GET/HEAD and only `trust: legacy` catalog records.
- Neither public boundary authenticates obsolete device credentials. The device API still refuses them with 401 `invalid_key`. No legacy upload implementation is restored.
- Artifact signatures are passed unchanged. Tauri authenticates the downloaded bytes with its existing public key. The server neither reads private keys nor replaces installed trust.

The catalog is deployment configuration supplied by the release owner, not a committed production artifact list. Missing catalog configuration fails closed. URLs never come from a request Host/query; stable HTTPS links omit credentials and signed queries. Release publication must verify availability before atomically publishing metadata. Odoo does not fetch arbitrary artifact URLs.

## Client preservation

Migration preserves SQLite rows, pending work, local paths/files, installation UID and the credential-store address. It quarantines old remote IDs and sessions transactionally and requires explicit rebinding; no mapping of old numeric IDs is inferred. Same-account reauthentication preserves valid migrated bindings. Uninstallers must retain application data; client code cannot restore deleted directories.

Normal device operations and updater traffic validate against their respective repository YAML documents. Native Odoo HTTP tests cover all legacy methods, malformed credentials, trust selection, no-update behavior, unsafe URLs/configuration, no mutation and continued device-key refusal. The opt-in real Odoo/Tauri updater fixture checks valid test-signed installation plus wrong-key, tampered and unavailable downloads with unchanged queued files and SQLite. These fixtures do not substitute for original installed releases.

## CI and browser integration

`ci-sync-app` includes both shared device/updater documents in relevant-change detection, requires Cargo and runs literal `task test:apps`, including Mobile. The prepared CI proposal is incorporated and superseded by this workflow. Hosted execution against the local integration commit remains unverified.

The desktop opens `GET /medilab/laboratory-files/<file_id>/edit` through the existing OS opener with the configured base path and no device/editor credentials or redirect query. The integrated page has actual browser login/return, native Office coediting, immutable Garage-save and Sync observer evidence. A headless component fixture is narrower than a complete graphical native desktop pilot. Non-root deployment requires the existing owner-approved proxy/application prefix decision and end-to-end ingress evidence; no desktop rewrite discards a configured prefix.

## Release gates

The release owner must identify installed versions/package types and verify existing-key availability without exposing keys, select the shipping scenario, publish real signed artifacts/download pages, and rehearse actual upgrade/uninstall/reinstall retention with isolated native OS credential stores. The CD workflow's package builds alone do not establish updater-signature publication. Production credentials and keys remain unchanged.

Unavailable old binaries cannot be retrofitted with a download-link UI by changing server JSON. The owner must demonstrate that identified legacy binaries support it or approve a revised notification/delivery path. New-client 410 presentation is verified separately.

Hosted required CI, Windows/macOS/native lifecycle evidence, production catalog/key inventory and the original-release scenarios remain open.

## Related documents

- [Sync updates](../../../../docs/specs/sync-updates.md)
- [Contract](contract.md)
- [Maintenance](maintenance.md)
- [Acceptance review](acceptance.md)
