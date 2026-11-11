# Sync updates and legacy compatibility

Stories: US-T23, US-T24, US-T25

## Goal

Publish eligible signed Sync updates and retire the legacy API without authenticating old device keys or changing local data. The [public contract](../../src/core/modules/sol_laboratory/api/sync-updates.openapi.yaml) is separate from the device API and the ONLYOFFICE callback.

## Routes

`GET /medilab/api/v1/updates/{target}/{arch}/{version}` is public native HTTP in the selected installation database. HEAD has the same status and headers with no body. It accepts one optional `channel`, defaulting to `stable`; other query parameters, repeated parameters and request bodies are refused. It never uses browser cookies, device keys, request Host values or caller download URLs as authority.

| Outcome | Status |
| --- | --- |
| A newer eligible artifact | 200, Tauri dynamic manifest with exact version, URL and signature, optional notes/date |
| No newer matching artifact | 204, empty body |
| Invalid target, architecture, semantic version or channel | 400, `invalid_request` |
| Other method | 405, `method_not_allowed`, `Allow: GET, HEAD` |
| Catalog absent, unreadable or invalid | 503, `update_unavailable` |

Every response has `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`. Versions use semantic version precedence, including numeric prerelease identifiers and ignored build metadata. Stable catalogs cannot contain prerelease versions. Channels are lowercase identifiers; releases are matched exactly by target, architecture, channel and trust boundary. Enumerated targets (`linux`, `windows`, `darwin`) and architectures (`x86_64`, `aarch64`) identify catalog entries; they do not certify native package support.

Every method at `/api/sync/v1`, its trailing slash and every descendant returns 410 `client_update_required`, except an explicitly enabled legacy updater GET/HEAD. Legacy requests require no valid credentials, perform no legacy operation and never echo credentials or bodies. The device API continues to refuse old or unissued keys with 401 `invalid_key`.

## Release configuration

| Variable | Meaning |
| --- | --- |
| `MEDILAB_SYNC_RELEASES_FILE` | Explicit local path to a read-only JSON release catalog |
| `MEDILAB_SYNC_DOWNLOAD_URL` | Stable public download page offered as `error.download_url` in legacy refusals |
| `MEDILAB_SYNC_LEGACY_UPDATER` | `manifest` enables the existing-trust legacy updater; unset or `manual` refuses legacy calls |

The release owner publishes artifacts first, verifies their availability and signatures with the intended installed trust, then atomically publishes the catalog. Odoo does not fetch artifact URLs or read signing keys. The desktop verifies artifact bytes with its existing configured public key; an unsigned manifest does not establish trust. A `legacy` record is eligible only after the owner verifies its signature against the actual installed public key. No server setting rotates or replaces client trust.

```json
{
  "releases": [
    {
      "target": "linux",
      "arch": "x86_64",
      "channel": "stable",
      "trust": "current",
      "version": "0.2.0",
      "url": "https://downloads.example/medilab-sync-update.tar.gz",
      "signature": "<base64 minisign signature text for the exact artifact>"
    }
  ]
}
```

The example is a shape, not a published artifact. The catalog schema is in the public contract's components. Files are limited to 1 MiB and 1,000 entries. Unknown fields, duplicate selections/versions, malformed signature encoding, unsafe URLs and invalid dates refuse the entire catalog. Optional dates include a time zone. An explicitly empty catalog yields 204; missing configuration yields 503.

Artifact and download URLs use HTTPS, without userinfo, queries, fragments, control characters, ambiguous encoding or traversal. Loopback HTTP is allowed for isolated fixtures. Unsafe or absent download-page configuration omits the action and leaves administrator guidance. No manifest or download action installs an artifact by itself.

When the existing signing key is available, the legacy updater serves only `trust: legacy` records at `/api/sync/v1/updates/{target}/{arch}/{version}`. New clients receive only `trust: current` records. With the manual migration scenario, the legacy updater also returns 410. The owner selects the shipping scenario after identifying installed releases, package types, signing-key availability and installer retention behavior. Until then, legacy calls fail closed; no production scenario or key is inferred.

## Verification

`TestLaboratorySyncUpdates` exercises normal HTTP contracts, both legacy modes, every legacy method/root/descendant, malformed credentials, selection, no downgrade, unsafe configurations and unchanged device authentication. `task test:openapi` validates and compares all three contracts. Sync's test adapter loads this exact updater YAML and checks real/mock updater requests and responses; drift-negative tests prove that changed required fields/headers fail.

The opt-in Rust test `updater_migration_tests::live_odoo_catalog_and_tauri_verifier_preserve_state_on_bad_downloads` uses an owned Odoo catalog, ephemeral test keys and actual Tauri download/install verification. It checks valid, wrong-key, tampered and unavailable artifacts while preserving fixture SQLite and queued files. It does not certify a previously released installer, OS credential store or native package lifecycle.

## Related documents

- [Laboratory files](laboratory-files.md)
- [Sync migration handoff](../../src/applications/medilab-sync/docs/migration-handoff.md)
