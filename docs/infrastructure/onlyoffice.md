# ONLYOFFICE deployment and recovery

Document Server is optional. Its failure refuses online editing while Odoo readiness, sync, history, download and restore keep working. Deployment acceptance covers EDT-01 through EDT-12 and OPS-01/02 of the [architecture decision](../decisions/laboratory-files-architecture.md). Production waits for the licence review and the real-service and staging gates below. The candidate applications are intentionally absent from the root application's resource list and have no automated sync.

## Deployment configuration

`infra/cluster/onlyoffice/` supplies a single Document Server, an HTTPS Service, retained 40 GiB `local-path` claim, certificates, Doppler ExternalSecret, ingress and default-deny network policy. The image is `onlyoffice/documentserver:9.4.0.1@sha256:3ab6ebc7c605e5a32b7ae3ff19daed4925090245acc8100ce2230bd766c88212`. Do not move to 10.0 without compatibility evidence and owner approval. Argo CD's candidate is `applications/onlyoffice.yaml`.

The pod requests two cores and 4 GiB, and is limited to four cores and 6 GiB. Its image requires root to initialize its bundled services; the service account token is absent, and seccomp uses RuntimeDefault. Resource sizing is a provisional starting point and needs concurrent editing and restart measurements. Recreate prevents two servers writing the same state; the hostname stays `onlyoffice` for RabbitMQ. Shutdown has 1350 seconds, exceeding one caller budget, but no rollout promises an uninterrupted editing session.

One claim holds `/var/lib/onlyoffice` (including `documentserver/App_Data/cache/files` and forgotten storage), `/var/www/onlyoffice/Data`, `/var/lib/postgresql`, `/var/lib/rabbitmq`, `/var/lib/redis` and custom fonts. PostgreSQL's schema and queue state are recovery dependencies, not replaceable empty directories. The local pinned amd64 image did not contain PostgreSQL/RabbitMQ/Redis binaries or their data directories, despite upstream defaults naming them and the tagged Dockerfile installing them. Its health/forgotten endpoints answered without those processes. Treat this image/source discrepancy as an activation blocker: establish the required state-service topology and initialization with an actual editor/save test before claiming those state paths are sufficient. The candidate reserves their paths but does not claim working embedded services. Argo pruning/deletion does not delete the claim. `local-path` survives a pod replacement on the same disk; it does not survive node/disk loss or provide replicated storage, encryption, snapshots or an independent archive. Claim protection does not change the storage class's reclaim policy. Never delete the claim or namespace during recovery.

`tools/infrastructure/onlyoffice/settings.json` and `start.sh` supply the local configuration; byte-identical copies inside the Kustomize root are enforced by tests. The wrapper loads NODE_CONFIG before the upstream entrypoint starts services, fixes JWT settings, disables raw logs and requires TLS material. Inspect effective non-secret settings on the running release; a YAML setting alone is not runtime evidence. Kubelet HTTPS probes check availability without certificate verification, so the independent monitor separately verifies the CA, hostname, status and exact `true` health body.

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

Merge the local override with the existing infrastructure Compose file, from the repository root, and select a unique project name and nonconflicting Odoo/database/Garage ports. Set ONLYOFFICE_JWT_SECRET through an isolated private environment file, and ONLYOFFICE_TLS_DIR/ONLYOFFICE_CA_DIR to throwaway certificate directories. Certificates need the service name `onlyoffice` and the browser hostname/loopback IP in their SANs. The override has no fixed container name, binds only loopback port 29843 by default, preserves all six state paths, disables untrusted TLS and uses the same runtime assets/digest as Kubernetes.

```sh
docker compose --env-file /secure/onlyoffice-local.env -p medilab-203-test \
  -f tools/infrastructure/docker-compose.yml \
  -f src/applications/medilab-sync/docker-compose.yml config --quiet
```

Document Server starts on a dedicated internal network with no default stack attachment. For actual editing, supply a reviewed fixture gateway for only the callback path and bucket origin, with trusted certificates and explicit host resolution; do not attach it directly to the shared default network or use host networking. This isolation is not proof of Kubernetes policy enforcement. CI validation renders the candidates and tests configuration/security invariants; actual browser/save/restart/policy tests remain separate.

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
- [Pinned Docker entrypoint](https://github.com/ONLYOFFICE/Docker-DocumentServer/blob/v9.4.0.1/run-document-server.sh)
