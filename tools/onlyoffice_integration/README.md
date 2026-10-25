# ONLYOFFICE callback integration tests

This opt-in harness uses real browser editors, pinned Document Server, Odoo, PostgreSQL and Garage. It uses a private test editor page, not the #230 page or Sync. The reviewed callback base is `fa8031db9eee3108211d771e09a57f20c038e4ad`; the separate verification branch starts at the official security fix `a3cec45f17f2429f99ae8556391c5750e38cc80a` and preserves test commit `27fa44c8436206765dd5bfa9f12099761af3f712` through a cherry-pick.

Required image:

```text
docker.io/onlyoffice/documentserver:9.4.0.1@sha256:3ab6ebc7c605e5a32b7ae3ff19daed4925090245acc8100ce2230bd766c88212
```

The runner verifies the live container image ID, repository digest, architecture, package version `9.4.0-129` and executable hashes. The image tag is 9.4.0.1; its command API reports 9.4.0.129.

## Run in an authorized local environment

Use Compose, registry access, the stored KietPham-VN GitHub CLI token and an already built compatible Odoo image. The image needs the bundled `base/tests/files/file.docx`, `file.xlsx` and `file.pptx` fixtures. Python contract tests require the dependencies in `src/core/pyproject.toml`.

```bash
export ONLYOFFICE_CONTAINER_SOCKET=/run/user/1000/podman/podman.sock
export ONLYOFFICE_COMPOSE_PROJECT=medilab171-agent4-newrun
export ONLYOFFICE_RUN_ID=newrun
export ONLYOFFICE_RUN_TIMEOUT=1200
export MEDILAB_ODOO_IMAGE=medilab-odoo:issue-171-callback
python3 tools/onlyoffice_integration/run.py preflight
python3 tools/onlyoffice_integration/run.py start
python3 tools/onlyoffice_integration/run.py test
```

Choose a new, owned project for a fresh run. No host ports are published. All networks, volumes and databases belong to the selected project. The runner refuses an existing acceptance container, database or evidence directory; it never removes them automatically. Its outer deadline stops only its named runner, preserving services and volumes. Individual engine commands also have deadlines. Podman Compose attach can hang after a container exits, so acceptance runs are detached and polled through the engine. Do not terminate a shared service or reuse another agent's resources.

Use the corrected production worker bootstrap for acceptance. The HTTP fixture retains the same pinned binaries, settings, sender correction and native configuration attestation as the TLS wrapper:

```bash
export ONLYOFFICE_COMPOSE_OVERRIDE="$PWD/tools/onlyoffice_integration/compose.runtime.yml"
export ONLYOFFICE_RUN_TIMEOUT=2400
export ONLYOFFICE_REAL_TAGS=onlyoffice_real,/sol_laboratory:TestLaboratoryEditingHttp,/sol_laboratory:TestLaboratoryEditingLogging,/sol_laboratory:TestOnlyofficeJwt
python3 tools/onlyoffice_integration/run.py start
python3 -m tools.onlyoffice_integration.probe_runtime
python3 tools/onlyoffice_integration/run.py test
```

The combined selection runs 15 real-service cases and 60 native HTTP/logging/JWT cases. The additional 650-second transaction case crosses the old ten-minute callback limit and requires the original delivery to return 503 before a fresh-JWT delivery commits. The original 370-second test remains. The fixture's Odoo HTTP worker uses the approved 1200-second limit; callback and whole-run waits are bounded separately. Full TLS startup, native policy drift rejection and restart/recreation are independently verified through the production wrapper; the HTTP adapter does not establish ingress, CNI or CDN acceptance.

For a further run against your own services after a restart, set a new `ONLYOFFICE_RUN_ID`, `ONLYOFFICE_RUNNER_SUFFIX` and `ONLYOFFICE_TEST_DATABASE` before `test`. Database names must start with `medilab171` and contain only lowercase letters, digits or underscores. The runner refuses an existing database or container; failed resources and evidence remain preserved. The local Odoo health loop retries connection/read timeouts within its existing 45-second startup deadline.

Preflight clears inherited GitHub token variables in child commands, selects the stored KietPham-VN token and verifies `gh api user --jq .login`. It changes neither shared authentication nor global Git configuration. It prints no token. Rootless Podman's authorized socket works on this host; the root socket remains inaccessible. No socket permissions or security controls need changing.

The browser build uses a read-only CA secret from `/etc/ssl/certs/ca-certificates.crt`; override `ONLYOFFICE_TEST_CA_BUNDLE` when needed. Certificate verification stays enabled. `ONLYOFFICE_CALLBACK_TEST_BUCKET` can select a fresh, owned callback bucket after an interrupted attempt; Garage setup provisions it. Do not remove ownership markers to bypass its guard.

## Selected cases and runtime comparison

Select both Odoo tags and the evidence expectations for a bounded isolated reproduction:

```bash
export ONLYOFFICE_TEST_METHOD=test_docx_many_editors_header_trimming
export ONLYOFFICE_REAL_TAGS=onlyoffice_real/sol_laboratory:TestOnlyofficeReal.test_docx_many_editors_header_trimming
export ONLYOFFICE_RUN_TIMEOUT=300
python3 tools/onlyoffice_integration/run.py test
```

The `onlyoffice_real` prefix matters: this class excludes `standard`. A bare module/class selector can silently select no test; missing evidence prevents acceptance.

The default fixture has body JWT enabled. For a fresh HTTP comparison with the exact committed #203 settings declaration:

```bash
python3 tools/onlyoffice_integration/runtime_env.py
export ONLYOFFICE_NODE_ENV_FILE="$PWD/.local/onlyoffice-node-contract.env"
export ONLYOFFICE_COMPOSE_OVERRIDE="$PWD/tools/onlyoffice_integration/compose.node-contract.yml"
python3 tools/onlyoffice_integration/run.py start
python3 -m tools.onlyoffice_integration.probe_runtime
```

The generator reads local commit `5b42e14f5715f21f85f525911cd8f692ae51302e` and creates a mode-0600 test environment file. This overlay deliberately reproduces the old declaration-only launch: it loses NODE_CONFIG when starting Supervisor and retains the large-history signing defect. Use it for a fresh failing baseline, with a separate project and evidence directory. The corrected `compose.runtime.yml` uses the mounted production worker bootstrap. Its probe requires policy read by `config.get` inside every native worker, bound to the current PID/start time, settings hash and pinned binary hash. Parent environment or disk declarations cannot produce a passing corrected probe. Callback body tokens remain present despite body JWT false and still require strict validation.

This comparison adapter uses isolated HTTP. It does not execute #203's full TLS entrypoint, trusted callback ingress, health/drain helper or Kubernetes policy. The full handoff remains in the infrastructure branch's committed `docs/infrastructure/onlyoffice.md`; do not copy its production manifests into this harness. Probe and scan available upstream logs without printing credentials:

```bash
python3 -m tools.onlyoffice_integration.probe_runtime
python3 -m tools.onlyoffice_integration.scan_logs
```

## Coverage

Fifteen native cases cover actual DOCX/XLSX/PPTX edits; first-delivery and later concurrent duplicates; fresh-JWT 503 redelivery; 200/error 1 negative control; finite exhaustion; real Garage outage; conflict versions; captured authentication refusals; long-name and 27-editor history; two Odoo-authorized DOCX editors; 370- and 650-second transaction retries crossing JWT expiry; and real invalid-certificate refusal. The many-editor regression is neither skipped nor xfailed. The sender runs the pinned history checker before signing either token; the Odoo verifier remains strict.

The relay forwards real callback bytes unchanged. Deliberate response injection and authenticated replay controls are labeled as such. Saved bytes come from Garage: SHA-256 must match the immutable version, an actual Office ZIP must contain the browser-inserted marker, attribution must match, and duplicate delivery must not add versions. Twenty-five participants in the large-history stress case are synthetic Document Server identities; the separate two-editor case checks real Odoo authorization.

The slow transaction trigger is installed on the main test thread. A bounded rendezvous releases the callback afterward, avoiding Odoo's registry-lock inversion. Child HTTP, relay, caller and whole-run deadlines remain explicit. This test proves the measured 370-second cycle, not the entire proposed deployment timing budget.

The read-only forgotten-output snapshot runs inside the owned network; keep its output protected and compare hashes before/after an explicitly controlled restart:

```bash
docker --host=unix:///run/user/1000/podman/podman.sock compose -p "$ONLYOFFICE_COMPOSE_PROJECT" -f tools/onlyoffice_integration/compose.yml run --no-deps --entrypoint python3 runner /opt/onlyoffice-integration/forgotten_probe.py
```

It signs only getForgottenList/getForgotten, validates the returned origin, refuses redirects and reports hashes, size and actual Office markers. It has no delete or replay operation. It was executed against retained real failed-save outputs; it does not make dirty-edit recovery automatic.

## Local checks and evidence

```bash
src/core/.venv/bin/python -m unittest tools.onlyoffice_integration.test_contract -v
src/core/.venv/bin/ruff check --config src/core/pyproject.toml tools/onlyoffice_integration
node --check tools/onlyoffice_integration/browser.cjs
```

The 29 contract tests preserve the original 24 and load actual pure JWT/origin/logging production code; namespace placeholders only avoid addon initialization. They do not substitute for Document Server execution. Seven Node tests cover sender ordering and trimming boundaries; 26 infrastructure Python tests cover deployment and effective-policy drift. CI runs the latter two suites. The double-encoded URL regression remains a normal passing test.

Private artifacts live under `.local/onlyoffice-agent4/<run-id>/`: runtime/source hashes, native outcomes, callback timing and token fingerprints, signature consistency, saved hashes/sizes/version counts and logging checks. Raw capabilities, JWTs, callback bodies and signed output URLs stay out of shared artifacts. The runner samples test names and outcomes while polling so engine log rotation cannot erase earlier case identities. Per-case cleanup records the real test-body outcome; absent logs/outcomes are classified unknown, never inferred passing from file presence. A successful acceptance still requires the native zero-failure summary, all evidence and exit 0.

For a native-only repeat, select fresh evidence/database/container identities as above, set `ONLYOFFICE_REAL_TAGS=/sol_laboratory:TestLaboratoryEditingHttp,/sol_laboratory:TestLaboratoryEditingLogging,/sol_laboratory:TestOnlyofficeJwt`, and run `python3 tools/onlyoffice_integration/run.py test-native`. This selection runs 60 native Odoo cases; it does not claim real-service callback coverage or require callback evidence files.

Preserve failed containers, databases, volumes and protected logs. The `down` command deletes owned volumes and is deliberately not part of the verification instructions. No staging or production acceptance follows from this local fixture.

## Related documents

- [Executed results and blockers](RESULTS.md)
- [Laboratory files specification](../../docs/specs/laboratory-files.md)
- [Testing conventions](../../docs/conventions/testing.md)
