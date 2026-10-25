# ONLYOFFICE deployment and recovery

Document Server is optional. Its failure refuses online editing while Odoo readiness, sync, history, download and restore keep working. Deployment acceptance covers EDT-01 through EDT-12 and OPS-01/02 of the [architecture decision](../decisions/laboratory-files-architecture.md). Production waits for the licence review and the real-service and staging gates below. The candidate applications are intentionally absent from the root application's resource list and have no automated sync.

## Deployment configuration

`infra/cluster/onlyoffice/` supplies a single Document Server, an HTTPS Service, retained 40 GiB `local-path` claim, certificates, Doppler ExternalSecret, ingress and default-deny network policy. The image is `onlyoffice/documentserver:9.4.0.1@sha256:3ab6ebc7c605e5a32b7ae3ff19daed4925090245acc8100ce2230bd766c88212`. Do not move to 10.0 without compatibility evidence and owner approval. Argo CD's candidate is `applications/onlyoffice.yaml`.

The pod requests two cores and 4 GiB, and is limited to four cores and 6 GiB. Root configures Nginx, file ownership and Supervisor, while docservice/converter run as `ds`. The service account token is absent, seccomp uses RuntimeDefault, privilege escalation is disabled and NET_RAW is dropped. Resource sizing needs concurrent editing measurements. Recreate keeps one writer; its rollout deadline is 2700 seconds to accommodate the 1890-second termination grace and 600-second startup probe budget.

Community Edition deliberately omits PostgreSQL, RabbitMQ and Redis. The registry-verified amd64 image has `PRODUCT_EDITION` empty; its entrypoint sets DB_AVAILABLE, RABBITMQ_AVAILABLE and REDIS_AVAILABLE false. Its build history installs those packages only for a nonempty commercial edition. The upstream [Community packaging change](https://github.com/ONLYOFFICE/Docker-DocumentServer/commit/11aafa4cce2c7cc3637648c8d965d9a5ee560ec3) documents this split. Generic SQL/RabbitMQ/Redis defaults and the tagged Dockerfile alone do not describe the Community artifact's required services. Do not add external databases or brokers to compensate for their absence. The exact packaged build is 9.4.0.129. Its entrypoint SHA-256 is `af598412e94e54832769cd388a91b4149c7b30f9b352774c3eb8cfd2aea6e8c3`; the registry config digest is `sha256:9f1f9ada40561752ba2597da8fe6e51fe7e09ba2b76cebdb4377ce004d88e5a3`. Corresponding-source/licence review still covers the actual artifact rather than assuming the tag is sufficient.

One claim holds `/var/lib/onlyoffice` (including `documentserver/App_Data/cache/files` and forgotten storage), `/var/www/onlyoffice/Data` and custom fonts, matching the Community image's non-log volumes. Logs are bounded memory. Keep all existing claim contents during upgrades until recovery verification, including unmounted subdirectories. No cleanup or database reconciliation is added. Argo pruning/deletion does not delete the claim. `local-path` survives replacement on the same disk; it supplies no node-loss recovery, encryption, replication or independent archive. Claim protection does not change the storage class's reclaim policy. Never delete the claim or namespace during recovery. Active Community process state must be tested independently of disk-cache survival; completed conversion output does not prove dirty editor changes or pending final saves survive a crash. The cache URL signing secret is independently generated once into `Data/.private/medilab-secure-link-secret`, with its directory mode 0700 and file mode 0600. Startup passes that retained key as SECURE_LINK_SECRET so replacement does not invalidate still-live cached-file URLs. Preserve this key with the cache and Data volume; do not print or rotate it during pending saves. This keeps existing signatures stable without extending their expiry or the JWT lifetime. An old signed URL returning 403 does not by itself establish lost bytes; distinguish key mismatch, URL expiry and missing cache data.

`tools/infrastructure/onlyoffice/` supplies the shared settings and startup, worker, health, shutdown and inspection helpers; byte-identical copies inside the Kustomize root are enforced by tests. Startup wires Supervisor to launch docservice and converter through `worker.sh`, which reads `settings.json` and exports NODE_CONFIG immediately before executing each binary. Exporting it only on PID 1 is insufficient because the upstream service launcher sanitizes that environment. Startup also validates trust readability as `ds`, keeps the JWT-bearing `local.json` mode 0600, disables raw logs and installs the checked drain helper. Its startup/readiness probe requires both supervised services running and a CA/hostname-verified HTTPS response whose body is exactly `true`. The probe resolves the configured certificate name to loopback, so startup never depends on an already-ready Service endpoint. Curl failure fails the probe even after a partial `true` response. Liveness checks the HTTPS listener only: a cache/storage failure must refuse new editing and alert, rather than trigger a pod restart that discards live process state. The independent monitor still verifies the external Service path and exact health body.

## Worker policy verification

Check the actual docservice and converter processes, not PID 1 or a merge of JSON files alone. The full native wrapper was reproduced with NODE_CONFIG present only on PID 1: both workers lacked it, leaving their file-based callback timeout at 10m and cache expiry at 86400 seconds. The per-worker bootstrap corrects that launch boundary and is idempotent when startup is rerun. Missing/empty settings fail before the worker executes. Both binaries keep their native process names and receive the exact committed policy after the service-launch environment is sanitized.

Set ONLYOFFICE_TEST_CONTAINER to the owned local test container and run:

```sh
podman exec --user ds "$ONLYOFFICE_TEST_CONTAINER" \
  python3 /opt/medilab/onlyoffice/inspect_config.py
```

The diagnostic checks both workers' NODE_ENV, NODE_CONFIG_DIR and NODE_CONFIG against the mounted settings. It reports only worker identity/PID, callback timeouts, cache horizon, selected outgoing-JWT settings and TLS verification. Expected values include 21m for both callback timeouts, cache_files=604800, Medilab-Editor-Token/Bearer/HS256/5m, inBody=false and TLS verification true. It refuses missing/mismatched worker environments; it never dumps the full environment or local.json. A root exec can lack permission to inspect ds processes with the configured privileges, so inspect as ds. Repeat after a fresh container start and after Supervisor restart. Full-wrapper local checks verified both workers at 21m/604800 and the committed JWT/TLS policy after fresh startup, Supervisor restart and full container restart, with a successful real DOCX-to-PDF conversion. These checks establish the worker policy environment; actual timeout behavior, callback compatibility and seven-day recoverability remain separate acceptance measurements.

## Secrets and TLS

Create `ONLYOFFICE_JWT_SECRET` in Doppler's `infra` config as a random secret of at least 32 base64url characters. The restricted alphabet also prevents the pinned entrypoint interpreting quotes as JavaScript. `onlyoffice-jwt` reads that secret; the integration variant gives the same key to Odoo. No default secret exists. JWT is required for browser, inbox and outbox, with `Medilab-Editor-Token`, `Bearer `, HS256, five-minute outbox expiry and no URL exclusion. `JWT_IN_BODY=false` is not a guarantee that outgoing bodies lack a token: the pinned sender also signs the body independently. Preserve and validate both signatures when presented, including large-history header trimming.

cert-manager creates a dedicated internal CA and a leaf for the service and callback ingress DNS names. Only public `ca.crt` from the leaf Secret is mounted into clients; never mount the CA signing key into Document Server or Odoo. Node extends public roots with NODE_EXTRA_CA_CERTS. The Odoo variant builds a combined public/internal Requests CA bundle in an init container. `USE_UNAUTHORIZED_STORAGE=false` and `requestDefaults.rejectUnauthorized=true` remain enforced. Rotation requires a controlled restart of Document Server, Odoo and the monitor after a new trust chain is available; drain editors first. Back up CA/state securely and test restore. Do not use `curl -k`, Requests `verify=False` or NODE_TLS_REJECT_UNAUTHORIZED=0.

## Network paths

| Caller | Destination | Required restriction |
| --- | --- | --- |
| Browser | `https://office.soltunemontepre.tech` | Cloudflare TLS, Tunnel, Traefik `web`, verified HTTPS to Document Server; Command Service denied on this public route |
| Odoo | `https://onlyoffice.medilab.svc.cluster.local` | Exact internal origin, verified CA; public saved URLs rewritten only from the exact configured public origin, retaining path/query and refusing redirects |
| Document Server | `https://onlyoffice-callback.kube-system.svc.cluster.local:8443` | Dedicated TLS Traefik entry point, only POST on `/medilab/laboratory-files/callback/`; existing Traefik-only Odoo ingress remains unchanged |
| Document Server | Approved bucket HTTPS endpoint | Exact provider endpoint and dedicated approved `/32` or `/128` egress; no other public/private service or metadata address |
| Document Server/monitor | CoreDNS | Selected DNS pods on TCP/UDP 53 only |
| Monitor | Document Server HTTPS health | No Odoo dependency; exact certificate and health body |

`onlyoffice-edge/` adds a callback Service and an additive ingress policy in `kube-system`; the existing `traefik-from-cloudflared` policy continues to restrict `web`. Its `traefik-values.yaml` must be merged into Ansible's HelmChartConfig to create port 8443, without exposing it in Traefik's normal Service or on the host. This port has 22-minute read/write/idle timeouts; its Odoo ServersTransport has a 22-minute response-header timeout. A route on the ordinary Cloudflare path is not an acceptable replacement for the callback path.

`onlyoffice-integration/` is an alternate source for the Odoo Application, deriving the existing Odoo manifests and patching environment/trust and callback routing. It sets ONLYOFFICE_INTERNAL_URL, ONLYOFFICE_PUBLIC_URL and ONLYOFFICE_CALLBACK_ORIGIN; the latter is the canonical origin expected by the editor page. Public Odoo routing excludes the native callback prefix. Activation requires the callback/page changes to be available in the released Odoo image; the base deployment's readiness probes are unchanged.

The checked-in policy deliberately grants no bucket egress. Before acceptance, add only approved endpoint addresses on TCP 443 in a reviewed environment policy, reconcile them with the bucket URL, certificate SANs and DNS, and test DNS changes. Shared CDN IPs do not establish an exact service boundary: use a dedicated endpoint or reviewed host-restricting egress proxy if addresses are shared. Never grant `0.0.0.0/0`, `::/0`, entire private ranges or direct Odoo access. `ALLOW_PRIVATE_IP_ADDRESS=true` is safe only together with effective network isolation; metadata access stays disabled. Standard NetworkPolicy is additive and does not restrict HTTP paths, DNS names, node-origin traffic or future broad policies. Audit the union of policies and service/DNAT behavior on the actual k3s CNI.

The public hostname is a proposed deployment name. It requires approved Cloudflare DNS/Tunnel configuration and TLS/browser tests before activation; Terraform has not been changed to publish it.

## Timing and bounded delivery

| Boundary | Configured value | Implication |
| --- | --- | --- |
| Outgoing JWT | 300 seconds | Each original request must authenticate before expiry; no JWT lifetime extension |
| Saved-document fetch | 900 seconds | A per-fetch bound; not the aggregate Odoo transaction deadline |
| Odoo worker | 1200 seconds wall, 600 seconds CPU | Unchanged limits; memory/commit/stream/retry work must fit |
| Document Server callback | 1260 seconds whole cycle and inactivity | Per delivery; configured through NODE_CONFIG |
| Internal callback proxy | 1320 seconds | Exceeds caller; measure every actual hop |
| Final-save retry | Initial plus three retries | Factor 2, 1000 ms minimum, no randomization, HTTP 429/500–599 or eligible network failure |

For one authenticated Odoo request the required envelope is `sum(fetch durations + bucket operations + lock waits + retry work + commit) < 1200s`, with CPU under 600s and memory under the worker/pod limits. One 900-second fetch leaves at most 300 seconds for everything else. Five internal attempts each capable of a 900-second fetch cannot fit. The four Document Server deliveries alone can consume `4*1260 + 1+2+4 = 5047s` (84 minutes 7 seconds), before queue/conversion/scheduling/shutdown overhead. This is a conditional caller envelope, not a guaranteed end-to-end deadline or a seven-day delivery promise.

An Odoo transaction retry after five minutes revalidates the original JWT; it cannot silently reuse authentication. #171's reviewed route may return 503 only when that request previously authenticated the final save before rollback. Initial expired/invalid tokens remain 403. Upstream `fillJwtForRequest()` signs queued redelivery afresh; actual delayed callback capture must prove this on the pinned image. HTTP 200/error 1 is a negative retry control, not a transport retry request. Restart/shutdown and activity notifications have different behavior.

**The aggregate timing guarantee is unproven.** Staging must measure slow/large saves, bucket upload, locks, DB commit and internal retries with the actual worker/pod settings. Do not extend JWTs, shorten fetches, change worker limits or introduce a total deadline without owner approval and #170 coordination. If the measured envelope exceeds any limit, acceptance fails.

## Shutdown contract

SIGTERM reaches the upstream Bash PID 1 through `exec`. The trap terminates its log-tail child, invokes `/usr/bin/documentserver-prepare4shutdown.sh`, and exits after draining; the remaining Nginx/Supervisor/service processes remain alive during the drain and end when the container exits. No preStop hook repeats the drain. Kubernetes must stop routing new sessions to the terminating endpoint while existing editing/save work settles; that path requires staging evidence.

The pinned shutdown algorithm has a mandatory 30-second settling interval, then checks remaining saves. Its source-derived ceiling is `30 + 1.5*(queue.visibilityTimeout + queue.retentionPeriod)` seconds: defaults 300 and 900 give 1830 seconds. A 30-second container stop races even an idle drain; the previous 1350-second grace did not cover this ceiling. Kubernetes and Compose use 1890 seconds, allowing sixty seconds beyond that source-derived ceiling. The local drain helper bounds its loopback PUT at 1860 seconds, bypasses inherited HTTP proxies and requires a successful transport and exact `true` response. A `200 false` or transport timeout exits unsuccessfully; the upstream helper's unconditional Done is not accepted as success. The 2700-second rollout deadline accommodates termination plus startup. These budgets do not extend the five-minute JWT, 900-second Odoo fetch, 1200-second worker or 1260-second callback limits.

Local idle tests completed the native PUT in 30.013 seconds, native SIGTERM in 30.197 seconds, and the validated helper/SIGTERM path in 30.249 seconds with exit 0 and both services observed running during drain. A completed synthetic DOCX conversion produced a valid PDF without the commercial services; the real converter refused an untrusted source certificate. Retaining the cache-signing key kept the identical 26,976-byte PDF reachable through the same signed URL after a clean stop/replacement (SHA-256 `c0aa6dc35858bb76b8c940a5f961bf60baae7a3a90d08bd8e4c2e9b84b97e43d`). These are idle/conversion-path observations, not proof of safe shutdown with dirty editor state or unfinished final saves. The upstream shutdown source also notes pre-existing long conversions need separate queue coverage. Increasing grace cannot repair a server that reports successful drain while work is unaccounted for. Agent 4 must test those paths below; false/timeout/forced-kill outcomes remain incidents with conditional byte recovery.

## Large-history callback release gate

Large-history compatibility remains an open production gate. Agent 4 reproduced a 27-editor-session signature/payload disagreement against its body-enabled runtime: an earlier body token signed full history while the transmitted payload/header carried empty history, and the reviewed callback correctly returned 403 with no version. That refusal is not an eligible HTTP retry status. Agent 4 withdrew its later claim that this also reproduced under the committed JWT_IN_BODY=false/NODE_CONFIG contract: rewriting local.json and restarting Supervisor had not established the effective process configuration. Do not classify the corrected runtime as passing or failing until both real workers pass the diagnostic above; a later native-process inspection found that parent NODE_CONFIG was sanitized before worker launch. Ordinary DOCX/XLSX/PPTX success does not establish overflow compatibility.

Independent pinned-source inspection identifies a risk to test: `sendServerRequest()` signs the body before `checkAndFixAuthorizationLength()` applies its hard-coded 7168-character threshold, clears history/change URL and regenerates only the header signature. It then attaches the earlier body token. This explains the body-enabled mismatch; how the exact packaged process emits or suppresses the token under the committed environment needs actual capture. Larger ingress header buffers alone do not change that source threshold. No configuration-only resolution is yet verified, and the ineffective-configuration cohort is not evidence against JWT_IN_BODY=false.

Preserve strict validation of every presented signature and its payload, native 403 on disagreement, the five-minute expiry and the current pin. Agent 4 must launch a fresh process with the exact committed NODE_CONFIG, establish its selected effective settings without disclosing secrets, and rerun ordinary and overflow controls. If it still fails, obtain owner approval before evaluating an upstream final-payload-signing correction/rebuilt digest, another tested release or a documented supported delivery mode. Do not suppress a presented body token, relax comparison, convert an authentication refusal into a retry response, enable unsigned callbacks or silently change versions. Any changed artifact retains its source/licence gate. Failed-save byte preservation and alert handoff must also be verified; a logged or expired session is not preservation.

## Monitoring and private diagnostics

`onlyoffice-monitor/` emits a fixed `onlyoffice_probe healthy=0|1` every 30 seconds with a five-second verified HTTPS deadline and no redirect/proxy use. It contains no document or credential data. Its independent Application is manual. Alloy's existing Kubernetes discovery sends this output to Loki. Candidate Grafana values provision a one-minute rule group for unhealthy/missing probes, #171's refusal/temporary/concurrency/terminal/internal failures and reconciliation findings. A two-minute missing-log window, one-minute evaluation, one-minute pending period and ten-second grouping target notification within five minutes, contingent on healthy delivery infrastructure. Rule parsing and actual notification latency require staging tests; logs alone do not prove alerts reach people.

`ONLYOFFICE_ALERT_WEBHOOK` is a separate Doppler secret delivered to Grafana in `monitoring` by `alerting-secret.yaml`. Select an operator-owned HTTPS receiver, merge `grafana-values.yaml` into the existing Grafana Application, preserving existing receivers/routing, and test receipt by both infrastructure operators and the MediLab maintainer. Its candidate root policy must be reconciled with any existing notification policy. No contact or external message is created by this change. Grafana/Loki/Alloy outage needs an independent external dead-man alert before production. No active alert delivery or acknowledgement guarantee is established by these files.

Every actionable save error opens an operator incident that survives session expiry and alert resolution. #171's sanitized callback status/outcome/session/correlation and `staged_bytes` evidence support correlation; the evidence is privileged and does not establish a committed version or retained bytes. Live aged-saving and unresolved expired-session detection is an acceptance dependency: absence of a callback log or an old `last_activity_at` is insufficient. Reconciliation regex alerts are a starting point and must be matched to actual emitted diagnostics. Do not close an incident because the session expired or retry logs stopped.

The wrapper disables log4js, Nginx access/error logging and raw entrypoint stdout/stderr; raw Document Server diagnostics cannot be forwarded to Loki/APM. Log directories are bounded memory rather than persistent recovery evidence. The callback ingress candidate also disables access logs/traces; its Traefik general output goes to `/dev/null` because error diagnostics can include signed URLs. This trades raw proxy diagnostics for fixed health signals. Odoo output-handler redaction from #171 must load before traffic, cover arbitrary loggers, watchdog/stack dumps and descendants, and be verified on the released prefork image. Extra exporters, sidecars, proxy/CDN analytics and APM need independent sentinel checks: disable request/response bodies, headers, callback path and query capture. Cloudflare must bypass cache and prevent credential-bearing URL collection/export. Page `no-store`/referrer behavior belongs to #230 and is checked through the actual CDN. Infrastructure config does not prove these external settings.

## Recovery runbook

Targets are seven days of actual recoverable bytes; alert in five minutes; acknowledge in thirty minutes; begin triage within two hours; and verified recovery or explicit unrecovered classification within twenty-four hours. Escalate after thirty minutes without acknowledgement or two hours without meaningful progress. Concrete primary/backup contacts and a private incident destination are required before service activation. Manual recovery only: no replay scheduler is installed.

1. Acknowledge and open a private incident. Record UTC detection/deadlines, session id, original document key, file/base version, correlation id, last known editor and failure class. Confirm current permissions; never include callback tokens, JWTs or signed URLs. Keep the incident open after the twelve-hour session expiry. At thirty minutes without acknowledgement escalate to the backup operator and maintainer; at two hours without meaningful progress escalate again.
2. Check fresh committed Odoo records, version hash/size and audit/conflict history before restoring. A lost response may already have committed. Classify transport outage, permanent authorization/configuration failure, integrity failure or confirmed absent bytes separately. A 404/410 is not proof of successful recovery.
3. Preserve all candidate bytes/state before restart, deletion, cleanup or upgrade. Take a consistent protected copy/snapshot of the complete claim and CA/state dependencies and verify it in isolation; a tar of a running database is not a consistent snapshot. Keep the source until verification. An Odoo staged object may be the sole complete copy: use privileged `staged_bytes` object key/hash/size evidence and provider recovery/version history or copy into an independently retained recovery archive immediately. #170's unchanged one-day orphan cleanup and immediate failed/duplicate deletion can beat a manual response. No deployment configuration here extends that cleanup.
4. From an authorized operator environment with service network access, invoke the signed server-only Command Service. Use a protected secret file and the configured CA; never paste a JWT or run with shell tracing. `recover.py` supports only `getForgottenList` and `getForgotten`, with a fresh five-minute HS256 header token. It refuses redirects and foreign origins, writes mode-0700 evidence directories and mode-0600 files, streams bytes with SHA-256/size, and prints no signed URL. An example is below. A missing forgotten entry is conditional evidence of loss; inspect protected cache/storage and provider recovery history before classifying.
5. Independently verify retrieved bytes, expected format, size and hash against available evidence. Record original key/session/base, retrieval source, actual operator and UTC times in the incident. A computed hash proves identity of retrieved bytes only after comparison; `retrieved_unverified` is not success. Test opening a safe copy, and preserve the original.
6. Restore through existing authorized upload/version/restore actions as the actual operator, retaining conflict rules and provenance. Never forge a callback, attribute the operator to the original editor, mutate an old version or bypass folder/sample checks. Recheck for a late committed callback to avoid duplicating an already recovered version. Verify the resulting committed version/hash/audit from a new transaction and independent download.
7. Within twenty-four hours record a verified outcome or explicitly mark **unrecovered**, including confirmed missing/corrupt bytes, unresolved availability and evidence preserved. Escalation continues even after that classification when appropriate. Never call an expired session, logs, inventory entry or older version a recovered final save. Do not invoke `deleteForgotten` or remove the last copy before verification and approved retention expiry.

```sh
python3 tools/infrastructure/onlyoffice/recover.py \
  --origin https://onlyoffice.medilab.svc.cluster.local \
  --ca /secure/onlyoffice-ca.crt --secret-file /secure/jwt-secret \
  --operator operator-account --output /secure/incident-inventory
# For a selected original document key, add --key ORIGINAL_KEY and use a new output directory.
```

`expire.files=604800` requests a seven-day cache horizon. Forgotten storage and retention are conditional on the save/conversion reaching that path and its bytes/state surviving. A cache expiry setting, retained PVC or logs do not supply continuous seven-day recoverability. Production requires tested independent recovery/version history for objects deleted immediately or after one day, plus consistent off-node state recovery for node loss. **The seven-day guarantee is unsupported until those restore tests pass.** No reconciliation logic or deletion age is changed.

## Local and CI contract

Merge the local override with the existing infrastructure Compose file, from the repository root, and select a unique project name and nonconflicting Odoo/database/Garage ports. Set ONLYOFFICE_JWT_SECRET through an isolated private environment file, and ONLYOFFICE_TLS_DIR/ONLYOFFICE_CA_DIR to throwaway certificate directories. Certificates need the service name `onlyoffice` and the browser hostname/loopback IP in their SANs. Keep private keys in the private TLS directory. Mount a separate public CA directory with mode 0755 and `ca.crt` mode 0644, readable by the container's `ds` user; a mode-0700 directory can make Node ignore the extra CA even when a root curl succeeds. Startup refuses an unreadable CA. Compose sets ONLYOFFICE_PROBE_HOST=onlyoffice; Kubernetes uses its certificate service DNS name. The override has no fixed container name, binds only loopback port 29843 by default, preserves the three Community state paths, disables untrusted TLS and uses the same runtime assets/digest as Kubernetes.

```sh
docker compose --env-file /secure/onlyoffice-local.env -p medilab-203-test \
  -f tools/infrastructure/docker-compose.yml \
  -f src/applications/medilab-sync/docker-compose.yml config --quiet
```

Document Server starts on a dedicated internal network with no default stack attachment. For actual editing, supply a reviewed fixture gateway for only the callback path and bucket origin, with trusted certificates and explicit host resolution; do not attach it directly to the shared default network or use host networking. This isolation is not proof of Kubernetes policy enforcement. CI validation renders the candidates and tests configuration/security invariants; actual browser/save/restart/policy tests remain separate.

## Agent 4 runtime handoff

Deliver this section manually; direct agent messaging is unavailable. Keep Agent 4's worktree, harness and resources under its ownership. Do not copy application source from this infrastructure branch into its reviewed callback tree. Record the exact reviewed callback SHA and its approved nested-path logging correction in protected test evidence. The reported correction `a3cec45f17f2429f99ae8556391c5750e38cc80a` is a candidate for that owner to confirm, not an infrastructure merge instruction.

Use the pinned index digest above and verify its amd64 child `sha256:e231bc62da8c1f0c1f78188f8c7e17e67716f38955d0ad1d703cf911ad6db84b`. Mount this branch's `tools/infrastructure/onlyoffice/` read-only at `/opt/medilab/onlyoffice`; run `/bin/bash /opt/medilab/onlyoffice/start.sh` as entrypoint. Supply the same isolated JWT secret as the reviewed callback through a protected env file, never command output. Mount private `tls.crt`/`tls.key` at `/run/onlyoffice-tls` and only readable public `ca.crt` at `/run/onlyoffice-ca`. Set ONLYOFFICE_PROBE_HOST to a certificate SAN (`onlyoffice` on the isolated stack), NGINX_WORKER_PROCESSES=2, no-new-privileges and cap-drop NET_RAW. Retain three separately identified volumes at `/var/lib/onlyoffice`, `/var/www/onlyoffice/Data`, and `/usr/share/fonts/truetype/custom`; bound `/var/log/onlyoffice` as 128 MiB tmpfs. Use four CPUs/6 GiB and a 1890-second stop grace. No PostgreSQL/RabbitMQ/Redis service or volume is needed for this Community image. Preserve the private cache-signing key in Data across replacement; do not regenerate it between deliveries. Preserve Agent 4's isolated network/ports and allow only its callback and trusted bucket fixture routes; do not attach the production namespace or credentials.

Launch both workers through the committed worker bootstrap and run the diagnostic above before classifying any integration result. Updating local.json, exporting NODE_CONFIG on the parent, or restarting an unmodified Supervisor configuration does not prove that policy reached either worker. A fresh start through `start.sh` wires the commands and then ordinary Supervisor restarts reload the same policy.

The shared settings require browser/inbox/outbox JWT, Medilab-Editor-Token, Bearer prefix, HS256, five-minute outgoing expiry, JWT_IN_BODY=false, TLS verification and private-address isolation. They set callback inactivity/whole-cycle to 21m, three retries with 1/2/4-second backoff on 429/500–599, no auto-assembly, and the seven-day cache request. Header and body tokens still both require validation. Verify these selected effective fields without dumping local.json, full environments or callback payloads. Confirm `ds` reads the CA, local.json is mode 0600, both supervised services run and the exact health helper succeeds. The callback origin is explicitly configured, not browser-derived; staging uses `https://onlyoffice-callback.kube-system.svc.cluster.local:8443/medilab/laboratory-files/callback/<capability>` behind the 22-minute proxy.

`PLUGINS_ENABLED=false` is retained. In the exact image entrypoint its only functional use is gating the startup `documentserver-pluginsmanager.sh --update=.../plugin-list-default.json` job; it is not a runtime prohibition on custom plugins and is not a complete marketplace access policy. A harness may specify its trusted fixture configuration URLs in `editorConfig.plugins.pluginsData` and identifiers in `editorConfig.plugins.autostart`, signing the completed editor configuration. Browser/CSP/TLS access to that fixture still needs to succeed. Do not re-enable distribution plugin initialization, add public network access, change JWT_IN_BODY, or weaken header/body validation to make the harness run. This distinction follows the packaged entrypoint and the [editor plugin configuration contract](https://api.onlyoffice.com/docs/docs-api/usage-api/config/editor/plugins); successful custom-plugin execution on the pinned browser remains Agent 4's actual test observation.

| Scenario | Required protected evidence |
| --- | --- |
| Idle SIGTERM | Time to positive drain, exit status, no SIGKILL, services alive while draining; allow the native 30-second floor |
| Dirty two-editor docx/xlsx/pptx | Signal while uncommitted changes exist; show the actual final bytes, committed version/hash or signed forgotten retrieval after restart; an idle exit 0 is insufficient |
| Pending final-save HTTP request | Slow the authenticated callback beyond 30 seconds; prove it completes or retains recoverable bytes before container exit, within real Odoo/caller/drain limits |
| 503, network failure, shutdown and exhaustion | Fresh header/body JWTs on eligible redelivery; finite attempts; document shutdown-specific retry suppression; a 200/error 1 remains a negative control |
| False drain, hung drain or forced kill | Failure classification, surviving/missing bytes and preserved evidence; do not translate process exit or session expiry into successful recovery |
| Restart/replacement | Reuse exactly the three owned volumes, retrieve actual final output with a fresh signed command, compare hash/size and Odoo committed history; separately test loss of process state and node storage |
| Privacy and route checks | No raw callback URL/JWT/query in ingress, DS, prefork/watchdog, Loki/APM/CDN sinks; public unversioned/versioned/case-variant Command Service paths refused |

Return sanitized counts, SHA-256/size, outcome classifications and protected artifact locations. Keep tokens, signed URLs and bodies out of shared reports. No automatic replay, forged callback, force-save enablement or reconciliation change is authorized by this handoff. The 1890-second grace is a proposed source-derived envelope; active-save acceptance and continuous seven-day recovery remain unproven until this matrix passes.

## Acceptance contract

Agent 4 can consume the following infrastructure test contract without modifying these files. All evidence records the Git SHA, image index/platform digest, timestamp, environment, test id, sanitized observation, protected artifact location and pass/fail/unproven result.

| ID | Required observation | Layer |
| --- | --- | --- |
| INF-CONFIG | Kustomize, core/CRD schemas, Application paths, ExternalSecret key parity, all state paths and Compose validation | Configuration |
| INF-TLS | Valid trusted CA succeeds; untrusted CA, wrong SAN and redirect fail for Document Server, Odoo fetch and monitoring | Local and staging |
| CB-JWT | Actual outgoing header/body signatures, five-minute exp, fresh queued JWT; long-history trimming for docx/xlsx/pptx preserves validation | Pinned service and staging |
| CB-TEMP | 503/error 1 retries at finite 1/2/4-second backoff; 200/error 1 does not; eligible network failure, shutdown and exhaustion classified | Pinned service and staging |
| OPS-TIME | 900-second fetch plus bucket/lock/retry/commit fits 1200-second worker and CPU/memory bounds; proxy exceeds 1260-second caller | Staging |
| INF-NET | Only public Host, exact callback POST path, approved bucket and DNS succeed; direct Odoo, wrong origins, redirects, other private services, metadata and arbitrary internet fail | Real CNI and staging |
| CB-LOSS | Real failed final save yields retrievable bytes; restart and pod replacement preserve all state; node-loss restore, provider cleanup/deletion recovery and seven-day verification succeed | Pinned service and staging |
| INF-PRIVACY | Sentinel custom/body JWT, encoded callback token and signed URL absent from ingress, app, watchdog, DS, Loki, APM and CDN sinks; filters precede traffic | Released image and staging |
| INF-ALERT | Inject down/stale/terminal/reconciliation failures, preserve incidents after expiry, receive notice in five minutes and exercise escalation/dead-man path | Staging with operators |
| PG-DOWN | Stop DS: Odoo ready, sync/history/download/restore work and editor visibly unavailable | Pinned service and staging |
| PG-OFFICE | Two authorized people edit docx/xlsx/pptx, save one version and exercise competing upload/conflict/history | Browser and staging |

No production cluster or credentials are used for local proof. Configuration validation and manually seeded persistence markers cannot close real failed-save, browser, policy or retention criteria.

## Infrastructure validation commands

Run from the infrastructure branch with its pinned Python dependencies and kubectl available:

```sh
python3 -m unittest discover -s tools/infrastructure/onlyoffice -p test_deployment.py
bash tools/infrastructure/onlyoffice/validate.sh
for script in tools/infrastructure/onlyoffice/*.sh; do bash -n "$script"; done
```

The schema script checks fourteen core resources and eighteen custom resources against checksum-pinned upstream schemas; the inherited Odoo Backup remains in its existing validation scope. The Compose merge command above validates isolation/configuration without starting services. These checks do not prove the Kubernetes CNI, the actual provider, alert delivery, active-save shutdown or retention. The local Traefik test verifies allowed health and refuses unversioned, versioned, uppercase and tested encoded Command Service paths plus a foreign Host; repeat against the deployed ingress/CDN.

## Activation gates

Before any activation, record accepted owner decisions in the infrastructure questions and deployment evidence: public hostname, dedicated bucket addresses/proxy, storage capacity/encryption/off-node recovery, primary/backup responders and receiver, licence reviewer, aggregate timing and delayed-token compatibility results. Preserve the existing issue assignees.

Record the release's AGPLv3 and section 7 terms, original logo/trademark restrictions, section 5 legal notices, CC BY-SA 4.0 interface/document terms, bundled component licences, corresponding-source offer, Community concurrent-editor limits and MediLab naming. Keep the actual reviewer, date, exact digest, source availability and written disposition. Unmodified upstream code does not waive these obligations. No completed licence review is claimed here.

Activation requires a reviewed environment change joining the candidate Argo applications, edge resources/Helm values, Odoo variant, endpoint policy, DNS/Tunnel and Grafana configuration. Confirm resource headroom and snapshot/restore/rotation tests before adding the applications to the root. Release only after the application redaction filters and independent monitoring are healthy; then enable browser/callback traffic. Rollback drains editors, preserves claim/CA and disables editing routes while Odoo stays available. Do not roll back persisted database schemas to an incompatible image without a verified state restore.

## Related documents

- [Architecture](architecture.md)
- [Cluster](cluster.md)
- [Secrets](secrets.md)
- [Laboratory files](../specs/laboratory-files.md)
- [Infrastructure questions](../../questions/infrastructure.md)
- [Pinned server defaults](https://github.com/ONLYOFFICE/server/blob/v9.4.0.1/Common/config/default.json)
- [Pinned callback sender](https://github.com/ONLYOFFICE/server/blob/v9.4.0.1/DocService/sources/DocsCoServer.js)
- [Pinned retry/forgotten behavior](https://github.com/ONLYOFFICE/server/blob/v9.4.0.1/DocService/sources/canvasservice.js)
- [Pinned shutdown algorithm](https://github.com/ONLYOFFICE/server/blob/v9.4.0.1/DocService/sources/shutdown.js)
- [Community packaging split](https://github.com/ONLYOFFICE/Docker-DocumentServer/commit/11aafa4cce2c7cc3637648c8d965d9a5ee560ec3)
- [Pinned Docker entrypoint](https://github.com/ONLYOFFICE/Docker-DocumentServer/blob/v9.4.0.1/run-document-server.sh)
