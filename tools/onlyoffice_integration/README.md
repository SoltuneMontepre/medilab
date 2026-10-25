# ONLYOFFICE callback integration tests

This opt-in harness runs the reviewed callback implementation with a real ONLYOFFICE browser editor, Document Server, Odoo, PostgreSQL and Garage. It does not use the #230 editor page. All changes are test code; application services, Sync and deployment manifests are unchanged.

The reviewed base is `fa8031db9eee3108211d771e09a57f20c038e4ad`. The required image is:

```text
docker.io/onlyoffice/documentserver:9.4.0.1@sha256:3ab6ebc7c605e5a32b7ae3ff19daed4925090245acc8100ce2230bd766c88212
```

The expected digest comes from `docs/specs/laboratory-files.md`. A configured pin alone does not verify a running image. `run.py` checks the launched container's image ID and repository digest, checks Debian package version `9.4.0-1`, and records runtime, architecture and source hashes before tests can pass.

## Run

Use a local Docker engine with Compose v2, the stored `KietPham-VN` GitHub CLI token, registry access, and the application's already built Odoo image. The addon directory is mounted from this worktree. The default application image is `medilab-odoo:local`; set `MEDILAB_ODOO_IMAGE` to select another compatible local image. The image must contain Odoo's bundled `base/tests/files/file.docx`, `file.xlsx` and `file.pptx` fixtures. A missing fixture fails the suite.

```bash
python3 tools/onlyoffice_integration/run.py preflight
python3 tools/onlyoffice_integration/run.py start
python3 tools/onlyoffice_integration/run.py test
```

`preflight` removes inherited GitHub tokens from its child environment, retrieves only the stored token for `KietPham-VN`, and requires `gh api user --jq .login` to equal that exact login. It does not switch shared authentication or write Git configuration. Tokens are neither printed nor persisted.

The Compose project is fixed to `medilab171-agent4`. It publishes no host ports, uses its own network and named volumes, and uses database `medilab171agent4` only inside its PostgreSQL service. The runner refuses a preexisting acceptance container or database. Do not reuse the project for other work. No other agent's stack is used. Docker context and endpoint overrides are cleared per command to select the local socket explicitly.

The browser build receives a read-only CA secret from `/etc/ssl/certs/ca-certificates.crt`; set `ONLYOFFICE_TEST_CA_BUNDLE` to the configured combined CA bundle if necessary. Preserve the Docker daemon's configured proxy and CA trust. The harness never disables certificate verification.

Failures preserve the stack for local investigation. After preserving required evidence, remove only this stack with:

```bash
python3 tools/onlyoffice_integration/run.py down
```

This explicitly deletes the harness's volumes. Run it before a new full acceptance run. It is not automatic recovery or a retained-byte archive.

## What is exercised

The opt-in `TestOnlyofficeReal` class reuses `LaboratoryEditingHttpCase`, its independent Odoo subprocess, committed transactions, real Garage proxy and audit assertions. Normal tests retain their existing URLs and behavior. The new class is tagged `onlyoffice_real` and excluded from `standard` runs. The existing HTTP tests continue to use fixture documents and make no Document Server compatibility claim.

A private relay serves a minimal test editor page and an autostart plugin. The plugin edits a real document using the Office API. A Playwright browser waits for the editor to acknowledge the change, destroys the editor, and disconnects. The test requires a real final status-2 callback. It reads the saved object back from Garage, verifies its SHA-256 against the immutable version, opens the Office ZIP and requires the unique inserted marker. It also checks attribution and version counts.

Ten opt-in cases cover:

- DOCX, XLSX and PPTX save, hash, actual edited bytes and audit provenance.
- Replays of a real final callback, including concurrent duplicate HTTP requests, without duplicate versions.
- One injected HTTP 503 followed by actual Document Server redelivery; both JWT issue times and fingerprints must change.
- HTTP 200/error 1 as a negative retry control, observed for 15 seconds after the first final delivery.
- Four total final deliveries under continuous injected HTTP 503, followed by a 15-second quiet window. This checks the default retry envelope, not arbitrary queue stalls.
- Real Garage 503 followed by actual Document Server redelivery and recovery.
- A concurrent file version that remains preserved while the editor produces a conflict version.
- Invalid signatures, missing tokens, header/body inconsistency, expired JWTs and wrong keys using a captured delivery; a large body-only signed duplicate verifies no additional version appears.
- A real HTTPS source with a self-signed certificate: Document Server conversion must fail with download error -4 before any source GET is received.

The harness does not forge a final save to stand in for an actual editor session. Authentication mutations and duplicate requests are explicitly replay controls after a real save. The temporary 503 and HTTP 200/error 1 controls are injected by the relay; the bucket failure is injected between Odoo and a real Garage server.

## Local checks

With the repository's Python dependencies installed:

```bash
src/core/.venv/bin/python -m unittest tools.onlyoffice_integration.test_contract -v
```

These load the actual pure JWT, origin-checking and logging services, using namespace placeholders only to avoid Odoo addon initialization. PyJWT verification is real. They do not start Odoo, a bucket or Document Server. The large signed payload and synthetic trimming cases verify authentication behavior only; they do not establish upstream trimming behavior.

One expected failure records a production redaction gap. To reproduce it as a failing assertion directly:

```bash
src/core/.venv/bin/python -c 'from tools.onlyoffice_integration.test_contract import TestContract; TestContract().test_double_encoded_callback_reference_is_redacted()'
```

## Evidence and limits

`run.py` writes `.local/onlyoffice-agent4/preflight.json`, `runtime.json`, `result.json` and one redacted JSON file per real test. Callback evidence includes timestamps, HTTP answers, token fingerprints, issue/expiry times and signature consistency. Save evidence includes source and bucket hashes, size, marker presence, attribution and version count. Raw JWTs, capabilities, callback bodies and saved URLs stay in memory. Raw service logs are not copied into these artifacts; upstream logs may contain credentials and require restricted local handling.

See [RESULTS.md](RESULTS.md) for executed checks and remaining acceptance gates. A clean test result requires all expected evidence files, a successful runner exit and Odoo's zero-failure summary. Staging and production acceptance require separate execution.

## Related documents

- [Laboratory files specification](../../docs/specs/laboratory-files.md)
- [Testing conventions](../../docs/conventions/testing.md)
- [ONLYOFFICE callback handler](https://api.onlyoffice.com/docs/docs-api/usage-api/callback-handler)
- [ONLYOFFICE plugin configuration](https://api.onlyoffice.com/docs/docs-api/usage-api/config/editor/plugins)
