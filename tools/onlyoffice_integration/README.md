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

The generator reads local commit `5b42e14f5715f21f85f525911cd8f692ae51302e` and creates a mode-0600 test environment file. The overlay declares body JWT false, the Node settings, bounded logs, four CPUs, 6 GiB, 1890-second stop grace and a third retained font volume. **A declaration is not effective configuration:** this pinned image loses NODE_CONFIG when starting supervisor. The worker probe demonstrated default 10-minute callback and one-day cache settings. Do not accept the proposed 21-minute/seven-day contract until the infrastructure owner fixes and independently verifies propagation. Callback body tokens also remain present despite body JWT false.

This comparison adapter uses isolated HTTP. It does not execute #203's full TLS entrypoint, trusted callback ingress, health/drain helper or Kubernetes policy. The full handoff remains in the infrastructure branch's committed `docs/infrastructure/onlyoffice.md`; do not copy its production manifests into this harness. Probe and scan available upstream logs without printing credentials:

```bash
python3 -m tools.onlyoffice_integration.probe_runtime
python3 -m tools.onlyoffice_integration.scan_logs
```

## Coverage

Fourteen native cases now cover actual DOCX/XLSX/PPTX edits; first-delivery and later concurrent duplicates; fresh-JWT 503 redelivery; 200/error 1 negative control; finite exhaustion; real Garage outage; conflict versions; captured authentication refusals; long-name and 27-editor history; two Odoo-authorized DOCX editors; a 370-second transaction retry crossing JWT expiry; and real invalid-certificate refusal. The many-editor regression intentionally fails on the current incompatibility and is neither skipped nor xfailed.

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

The 24 contract tests load actual pure JWT/origin/logging production code; namespace placeholders only avoid addon initialization. They do not substitute for Document Server execution. The former double-encoded URL failure now passes normally on a3cec45.

Private artifacts live under `.local/onlyoffice-agent4/<run-id>/`: runtime/source hashes, native outcomes, callback timing and token fingerprints, signature consistency, saved hashes/sizes/version counts and logging checks. Raw capabilities, JWTs, callback bodies and signed output URLs stay out of shared artifacts. Per-case cleanup records the test-body outcome; absent logs/outcomes are classified unknown, never inferred passing from file presence. A successful acceptance still requires the native zero-failure summary, all evidence and exit 0.

Preserve failed containers, databases, volumes and protected logs. The `down` command deletes owned volumes and is deliberately not part of the verification instructions. No staging or production acceptance follows from this local fixture.

## Related documents

- [Executed results and blockers](RESULTS.md)
- [Laboratory files specification](../../docs/specs/laboratory-files.md)
- [Testing conventions](../../docs/conventions/testing.md)
