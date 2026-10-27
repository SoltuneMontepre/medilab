# ONLYOFFICE callback integration tests

This opt-in harness uses real browser editors, pinned Document Server, Odoo, PostgreSQL and Garage. The callback stress cases use a private test editor page. The separate released-page probe below uses the actual #230 page and native browser keyboard input. Neither launches the complete native Sync UI. The reviewed callback base is `fa8031db9eee3108211d771e09a57f20c038e4ad`; the separate verification branch starts at the official security fix `a3cec45f17f2429f99ae8556391c5750e38cc80a` and preserves test commit `27fa44c8436206765dd5bfa9f12099761af3f712` through a cherry-pick.

Required image:

```text
docker.io/onlyoffice/documentserver:9.4.0.1@sha256:3ab6ebc7c605e5a32b7ae3ff19daed4925090245acc8100ce2230bd766c88212
```

The runner verifies the live container image ID, repository digest, architecture, package version `9.4.0-129` and executable hashes. The image tag is 9.4.0.1; its command API reports 9.4.0.129.

## Run in an authorized local environment

Use Compose, the OpenSSL CLI, registry access, the stored KietPham-VN GitHub CLI token and an already built compatible Odoo image. The image needs the bundled `base/tests/files/file.docx`, `file.xlsx` and `file.pptx` fixtures. Python contract tests require the dependencies in `src/core/pyproject.toml`.

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

The runner creates the project bridge explicitly with `--internal --opt isolate=strict` before Compose starts. Compose treats that named bridge as external to its own network creation, but the runner verifies the exact project label, strict isolation setting, every running peer's ownership and single-network attachment, and the absence of published ports or engine sockets. Podman Compose did not propagate `driver_opts.isolate`; declaring the option in Compose alone left inbound traffic from another bridge reachable. An existing network without the required metadata fails closed. Use a new project name instead of altering or removing a retained fixture. Build/download dependencies before attaching offline helpers to the bridge; helpers must be project-labeled and use only this bridge. This boundary is for synthetic fixtures and does not establish production ingress or CNI isolation.

Use the canonical production TLS entrypoint and worker bootstrap for acceptance. The fixture retains the pinned binaries, settings, sender correction and native configuration attestation:

```bash
export ONLYOFFICE_COMPOSE_OVERRIDE="$PWD/tools/onlyoffice_integration/compose.runtime.yml"
export ONLYOFFICE_RUN_TIMEOUT=2400
export ONLYOFFICE_REAL_TAGS=onlyoffice_real,/sol_laboratory:TestLaboratoryEditingHttp,/sol_laboratory:TestLaboratoryEditingLogging,/sol_laboratory:TestOnlyofficeJwt
python3 tools/onlyoffice_integration/run.py start
python3 -m tools.onlyoffice_integration.probe_runtime
python3 tools/onlyoffice_integration/run.py test
```

The combined selection runs the real-service cases and native HTTP/logging/JWT cases. The additional 650-second transaction case crosses the old ten-minute callback limit and requires the original delivery to return 503 before a fresh-JWT delivery commits. The original 370-second test remains. The fixture's Odoo HTTP worker uses the approved 1200-second limit; callback and whole-run waits are bounded separately. Full TLS startup, native policy drift rejection and restart/recreation are independently verified through the production wrapper; the isolated fixture does not establish deployed ingress, CNI or CDN acceptance.

For a further run against your own services after a restart, set a new `ONLYOFFICE_RUN_ID`, `ONLYOFFICE_RUNNER_SUFFIX` and `ONLYOFFICE_TEST_DATABASE` before `test`. Database names must start with `medilab171` and contain only lowercase letters, digits or underscores. The runner refuses an existing database or container; failed resources and evidence remain preserved. The local Odoo health loop retries connection/read timeouts within its existing 45-second startup deadline.

Preflight clears inherited GitHub token variables in child commands, selects the stored KietPham-VN token and verifies `gh api user --jq .login`. It changes neither shared authentication nor global Git configuration. It prints no token. Rootless Podman's authorized socket works on this host; the root socket remains inaccessible. No socket permissions or security controls need changing.

The browser build uses a read-only CA secret from `/etc/ssl/certs/ca-certificates.crt`; override `ONLYOFFICE_TEST_CA_BUNDLE` when needed. Certificate verification stays enabled. `ONLYOFFICE_CALLBACK_TEST_BUCKET` can select a fresh, owned callback bucket after an interrupted attempt; Garage setup provisions it. Do not remove ownership markers to bypass its guard.

## Fixture TLS identities

`run.py start` creates an owned two-day CA and separate Document Server, Garage-gateway and loopback leaf identities under `.local/onlyoffice-tls/<project>`. The CA signing key stays on the host; peers receive only their leaf key and public CA. Private keys use mode 0600. The browser imports the public CA into its own NSS database and runs as `pwuser`. A guarded runner gets a unique certificate for `runner` and its container hostname, then drops to the image's Odoo user with an explicit data directory. Existing/expired/foreign identities fail closed; use a fresh guarded project or runner suffix. `.local` is excluded from container build context. No certificate or hostname verification bypass is used.

Document Server uses the canonical TLS entrypoint. Browser proxies listen on HTTPS loopback origins and validate backend certificate names independently of the preserved signed Host header. Garage's S3 endpoint is a Unix socket shared only with the TLS gateway. The real callback/plugin relay also uses verified TLS, avoiding mixed-content plugins. Native Odoo HTTP/control endpoints remain isolated synthetic fixtures; this is not a claim that every test-control hop is encrypted.

For the manual Compose inspection/page commands below, select the same generated identities as the runner:

```bash
export ONLYOFFICE_FIXTURE_TLS_DIRECTORY="$PWD/.local/onlyoffice-tls/$ONLYOFFICE_COMPOSE_PROJECT"
export ONLYOFFICE_RUNNER_HOSTNAME="$ONLYOFFICE_COMPOSE_PROJECT-acceptance"
```

`run.py` computes the actual suffixed runner hostname itself before issuing its certificate. Keep the default fixture CA/leaf mounts when adding page/Rust helpers. Do not mount the CA signing key or relax peer verification.

## Selected cases and runtime comparison

Select both Odoo tags and the evidence expectations for a bounded isolated reproduction:

```bash
export ONLYOFFICE_TEST_METHOD=test_docx_many_editors_header_trimming
export ONLYOFFICE_REAL_TAGS=onlyoffice_real/sol_laboratory:TestOnlyofficeReal.test_docx_many_editors_header_trimming
export ONLYOFFICE_RUN_TIMEOUT=300
python3 tools/onlyoffice_integration/run.py test
```

The `onlyoffice_real` prefix matters: this class excludes `standard`. A bare module/class selector can silently select no test; missing evidence prevents acceptance.

The default fixture has body JWT enabled. The environment generator reads canonical policy from the verified P1 revision `e6f24173c831eac945fc90cd50af4a6f788ba2c6`; `--commit` accepts an exact integrated revision. Its policy bytes match the earlier infrastructure declaration. For a fresh worker-policy comparison with that committed policy:

```bash
python3 tools/onlyoffice_integration/runtime_env.py
export ONLYOFFICE_NODE_ENV_FILE="$PWD/.local/onlyoffice-node-contract.env"
export ONLYOFFICE_COMPOSE_OVERRIDE="$PWD/tools/onlyoffice_integration/compose.node-contract.yml"
python3 tools/onlyoffice_integration/run.py start
python3 -m tools.onlyoffice_integration.probe_runtime
```

The generator reads local commit `5b42e14f5715f21f85f525911cd8f692ae51302e` and creates a mode-0600 test environment file. This overlay deliberately reproduces the old declaration-only launch: it loses NODE_CONFIG when starting Supervisor and retains the large-history signing defect. Use it for a fresh failing baseline, with a separate project and evidence directory. The corrected `compose.runtime.yml` uses the mounted production worker bootstrap. Its probe requires policy read by `config.get` inside every native worker, bound to the current PID/start time, settings hash and pinned binary hash. Parent environment or disk declarations cannot produce a passing corrected probe. Callback body tokens remain present despite body JWT false and still require strict validation. Output must be a new file beneath this worktree's `.local` directory; existing files and symbolic-link outputs are refused. Use a fresh `--output` path for another comparison.

This comparison adapter uses the fixture TLS listeners but bypasses the canonical worker bootstrap. It does not execute the full TLS entrypoint, deployed callback ingress, health/drain helper or Kubernetes policy. The full handoff remains in the infrastructure branch's committed `docs/infrastructure/onlyoffice.md`; do not copy its production manifests into this harness. Probe and scan available upstream logs without printing credentials:

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

## Released editor page

After starting an owned runtime project, add the page browser and Document Server loopback storage proxy. The storage adapter requires the explicit `MEDILAB_ONLYOFFICE_STORAGE_FIXTURE=isolated-owned` opt-in and container runtime markers. Its verified TLS listener binds only `127.0.0.1:3900`, sends only owned bucket paths over TLS to the fixed Garage gateway, and forwards no caller credentials. The gateway forwards locally over a shared Unix socket; Garage exposes no plaintext S3 TCP listener. This transport remains a disposable fixture, separate from production storage. The environment and runtime markers record intended use; they do not authenticate ownership or prove isolation. Network/container inspection must establish the actual boundary:

```bash
docker --host=unix:///run/user/1000/podman/podman.sock compose -p "$ONLYOFFICE_COMPOSE_PROJECT" \
  -f tools/onlyoffice_integration/compose.yml -f tools/onlyoffice_integration/compose.page.yml up -d page-browser
podman exec -d -e MEDILAB_ONLYOFFICE_STORAGE_FIXTURE=isolated-owned "$ONLYOFFICE_COMPOSE_PROJECT-documentserver-1" \
  python3 /opt/onlyoffice-integration/loopback_storage_proxy.py
export ONLYOFFICE_CALLBACK_TEST_BUCKET=laboratory-files-integration-page
docker --host=unix:///run/user/1000/podman/podman.sock compose -p "$ONLYOFFICE_COMPOSE_PROJECT" \
  -f tools/onlyoffice_integration/compose.yml run --rm --no-deps garage-setup
export ONLYOFFICE_COMPOSE_OVERRIDE="$PWD/tools/onlyoffice_integration/compose.page.yml"
export ONLYOFFICE_REAL_TAGS=onlyoffice_page_real
export ONLYOFFICE_RUN_ID=page
export ONLYOFFICE_RUNNER_SUFFIX=page
export ONLYOFFICE_TEST_DATABASE=medilab171page
export ONLYOFFICE_RUN_TIMEOUT=480
python3 tools/onlyoffice_integration/run.py test-native
```

Use fresh guarded identities and a bucket not owned by another active database. Serialize browser runners: the callback harness requires a `runner` DNS alias; native-only runners omit it. Callback origins use the fixture container's unique hostname because Document Server can cache service-name DNS across ephemeral runners. Do not restart or recreate another owner's services.

The page probe starts with no editing session, follows native CSRF-protected admin login/return, loads the released signed configuration, types into the native DOCX canvas, closes, and checks one new immutable version, attribution, Office XML marker and actual Garage SHA-256. `page-docx.json` records the real-service result; `test-native` describes the Odoo runner and its summary, not a callback stress cohort. The storage proxy permits objects only in the owned `laboratory-files` bucket namespace, including fresh suffixed fixture buckets, and rejects literal/encoded traversal, separators and controls while preserving signed queries. The loopback proxies keep the existing public-origin checks intact while using verified TLS, with backend SNI fixed independently of the signed Host header; they do not establish deployed TLS/CNI behavior. No production key, verifier bypass or resigned browser configuration is used.

For a real elapsed credential-lifetime case, choose fresh run/database identities and set `ONLYOFFICE_PAGE_HOLD_SECONDS=920` and `ONLYOFFICE_RUN_TIMEOUT=1400`. The native editor holds its changes beyond the original fifteen-minute configuration lifetime before closing and saving. This does not simulate seven-day recovery, initial expired-token admission or a complete native desktop pilot. Browser failures retain a protected screenshot inside the owned page browser and fixed-stage diagnostics; never publish raw page configuration or callback logs.

To observe the resulting page save with the actual Sync Rust client, use a fresh short-run identity, set `ONLYOFFICE_DESKTOP_PROBE=1` and `ONLYOFFICE_DESKTOP_CONTAINER` to an owned `medilab-integration-*` Rust fixture on the same private network. It must mount the required source/API paths beneath `/workspace`, have the locked Rust dependencies/Linux libraries, and run `loopback_storage_proxy.py` with the explicit fixture opt-in, loopback leaf identity and public fixture CA. The observer validates helper ownership/isolation before passing its synthetic login. Only the ignored observer test adds this explicit CA for `https://localhost:3900`; production Rust client trust settings are unchanged. Run `python3 -m tools.onlyoffice_integration.page_sync` instead of the direct runner. The bounded rendezvous occurs after database transactions close; the observer signs in with the disposable database's default administrator, checks file/history/hash/source and downloads the exact bytes through the normal contract-checked API client, then revokes its unique device. No key/callback authority is passed in the browser URL.

Launch persistent Rust/Cypress helper containers with `--init` or a signal-handling supervisor. A bare `sleep infinity` as PID 1 ignores default SIGTERM and can reach the stop timeout even after every test has finished. Stop only owned fixtures and record exit status; retain timeout/forced-shutdown evidence rather than labeling it graceful shutdown. The Compose browser fixtures already enable init.

The explicit `onlyoffice_down_real` case is run only after stopping this owned Document Server, with `ONLYOFFICE_PAGE_DOWN=1`. Use a fresh Compose runner/database/bucket, omit `--use-aliases`, and select that tag directly; `run.py` correctly requires a running pinned server and therefore is not the launcher for a stopped-server scenario. The case logs in through normal HTTP, verifies the real editor refusal and no session/version mutation, and checks API readiness while the service is unavailable. Restart the owned service, reattest its workers, compare retained output hashes and rerun normal saves before concluding local lifecycle acceptance.

## Local checks and evidence

```bash
src/core/.venv/bin/python -m unittest tools.onlyoffice_integration.test_contract -v
src/core/.venv/bin/ruff check --config src/core/pyproject.toml tools/onlyoffice_integration
node --check tools/onlyoffice_integration/browser.cjs
```

The integration suite loads actual JWT/origin/logging production code; namespace placeholders only avoid addon initialization. It does not substitute for Document Server execution. Native result parsing is separate from engine orchestration: test_native_results.py and test_runner.py verify that rotated logs retain failures, missing evidence and zero-test runs cannot claim acceptance, and timeouts stop only the selected runner. The signing tests load the real signing hook through a bounded module-loader fixture and cover sender ordering and trimming boundaries. Infrastructure Python tests cover deployment, effective-policy drift and the monitor. The deployed runtime source is canonical under infra/cluster/onlyoffice; local fixtures mount those exact files rather than keeping duplicate copies. CI runs these suites, including the double-encoded URL regression.

Runner evidence uses a private per-database directory beneath `/var/lib/odoo/onlyoffice-integration`, copied into `.local/onlyoffice-agent4/<run-id>/`. Browser failure screenshots use an owner-only temporary directory. Private artifacts include: runtime/source hashes, native outcomes, callback timing and token fingerprints, signature consistency, saved hashes/sizes/version counts and logging checks. Raw capabilities, JWTs, callback bodies and signed output URLs stay out of shared artifacts. The runner samples test names and outcomes while polling so engine log rotation cannot erase earlier case identities. Per-case cleanup records the real test-body outcome; absent logs/outcomes are classified unknown, never inferred passing from file presence. A successful acceptance still requires the native zero-failure summary, all evidence and exit 0.

For a native-only repeat, select fresh evidence/database/container identities as above, set `ONLYOFFICE_REAL_TAGS=/sol_laboratory:TestLaboratoryEditingHttp,/sol_laboratory:TestLaboratoryEditingLogging,/sol_laboratory:TestOnlyofficeJwt`, and run `python3 tools/onlyoffice_integration/run.py test-native`. This selection runs 60 native Odoo cases; it does not claim real-service callback coverage or require callback evidence files.

Preserve failed containers, databases, volumes and protected logs. The `down` command deletes owned volumes and is deliberately not part of the verification instructions. No staging or production acceptance follows from this local fixture.

## Related documents

- [Laboratory files specification](../../docs/specs/laboratory-files.md)
- [Testing conventions](../../docs/conventions/testing.md)

The browser image defaults to `pwuser`. The owned browser/page Compose services explicitly start the trusted key/NSS initializer as root, then execute Node as `pwuser`. The Garage gateway explicitly uses root to read its mode-0600 mounted leaf key, with all capabilities dropped, no-new-privileges and a read-only root filesystem; it has no host publications, production mounts or engine socket. Its S3 Unix socket is shared only with Garage. The gateway allows the fixture S3 header/encoding/checksum contract and refuses redirects and foreign/noncanonical request authorities. Disposable CA certificates declare critical CA constraints and signing Key Usage for strict contemporary Python verification. Linux test certificate generation uses `/usr/bin/openssl`; no fixture key is committed.
