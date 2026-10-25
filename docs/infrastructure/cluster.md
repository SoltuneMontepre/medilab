# Cluster

What Argo CD deploys from `infra/cluster/` onto the cluster in [Architecture](architecture.md), once Ansible has installed k3s and Argo CD; see [Provisioning](provisioning.md).

## Layout

`infra/cluster/` is the path of the `medilab` root application. Its `kustomization.yaml` lists one Argo CD `Application` per component, in `infra/cluster/applications/`:

| Application           | Deploys                                                                    | Source                             | Namespace          | Wave |
| --------------------- | -------------------------------------------------------------------------- | ---------------------------------- | ------------------ | ---- |
| `cert-manager`        | cert-manager, which issues the TLS certificates of the Barman Cloud plugin | `cert-manager` chart               | `cert-manager`     | -3   |
| `external-secrets`    | External Secrets Operator                                                  | `external-secrets` chart           | `external-secrets` | -3   |
| `secret-store`        | The `doppler` `ClusterSecretStore`                                         | `infra/cluster/secret-store`       | `external-secrets` | -2   |
| `cloudnative-pg`      | The CloudNativePG operator                                                 | `cloudnative-pg` chart             | `cnpg-system`      | -2   |
| `plugin-barman-cloud` | The Barman Cloud plugin of CloudNativePG                                   | `plugin-barman-cloud` chart        | `cnpg-system`      | -1   |
| `database`            | The Postgres `Cluster`, its object store and its scheduled backup          | `infra/cluster/database`           | `medilab`          | 0    |
| `cloudflared`         | The Cloudflare Tunnel connector                                            | `infra/cluster/cloudflared`        | `medilab`          | 1    |
| `mailpit`             | Mailpit, which catches the e-mail Odoo sends                               | `infra/cluster/mailpit`            | `medilab`          | 1    |
| `cloudbeaver`         | CloudBeaver, connected to the `medilab` database                           | `infra/cluster/cloudbeaver`        | `medilab`          | 1    |
| `odoo`                | Odoo, the pre-sync backup and the upgrade Job                              | `infra/cluster/odoo`               | `medilab`          | 1    |
| `loki`                | Loki, which stores the logs of every pod                                   | `loki` chart                       | `monitoring`       | 1    |
| `alloy`               | Alloy, which sends the logs of every pod to Loki                           | `alloy` chart                      | `monitoring`       | 2    |
| `grafana`             | Grafana, which shows the logs in Loki                                      | `grafana` chart                    | `monitoring`       | 2    |
| `grafana-dashboards`  | The Grafana dashboards                                                     | `infra/cluster/grafana-dashboards` | `monitoring`       | 1    |

- The root application syncs the applications wave by wave and waits until every application of a wave is healthy before the next. Argo CD has no health check for an `Application` by default; the `argocd` role adds one.
- Every application syncs automatically, prunes what was removed from Git and reverts changes made by hand. Every application except `odoo` retries a failed sync five times, so the first install settles while operators and their CRDs come up.
- The `database` application never prunes or deletes the `Cluster`, even when it is removed from Git.

## Versions

Every chart and image is pinned and upgraded by changing it in `infra/cluster/`:

| What                      | Version  | Where                                   |
| ------------------------- | -------- | --------------------------------------- |
| cert-manager chart        | v1.21.2  | `applications/cert-manager.yaml`        |
| External Secrets chart    | 2.13.0   | `applications/external-secrets.yaml`    |
| CloudNativePG chart       | 0.29.1   | `applications/cloudnative-pg.yaml`      |
| Barman Cloud plugin chart | 0.8.1    | `applications/plugin-barman-cloud.yaml` |
| Postgres image            | 18.4     | `imageName` in `database/cluster.yaml`  |
| `cloudflared` image       | 2026.9.3 | `cloudflared/deployment.yaml`           |
| Mailpit image             | v1.31.6  | `mailpit/deployment.yaml`               |
| CloudBeaver image         | 26.2.2   | `cloudbeaver/deployment.yaml`           |
| Loki chart                | 7.5.0    | `applications/loki.yaml`                |
| Alloy chart               | 1.14.3   | `applications/alloy.yaml`               |
| Grafana chart             | 14.0.1   | `applications/grafana.yaml`             |
| MediLab image             | released | `newTag` in `odoo/kustomization.yaml`   |

`cd-core` releases the MediLab image by committing its tag to `newTag`; see [Pipelines](pipelines.md#cd-core).

## Secrets

External Secrets reads the Doppler `infra` config through the `doppler` `ClusterSecretStore`, with the service token that Ansible stores in the `doppler-token` Secret of the `external-secrets` namespace. Each component gets its own Secret, refreshed every hour:

| Secret               | Doppler secrets                                                          | Used by                    |
| -------------------- | ------------------------------------------------------------------------ | -------------------------- |
| `backup-bucket`      | `BUCKET_ADDRESS`, `BUCKET_BACKUP_ACCESS_KEY`, `BUCKET_BACKUP_SECRET_KEY` | The `backups` object store |
| `filestore-bucket`   | `BUCKET_ADDRESS`, `BUCKET_MAIN_ACCESS_KEY`, `BUCKET_MAIN_SECRET_KEY`     | Odoo and the upgrade Job   |
| `cloudflared-tunnel` | `CLOUDFLARE_TUNNEL_TOKEN`                                                | `cloudflared`              |
| `odoo-config`        | `ODOO_ADMIN_PASSWORD`, written into `odoo.conf`                          | Odoo and the upgrade Job   |
| `mailpit-ui-auth`    | `MAILPIT_UI_AUTH`                                                        | Mailpit                    |
| `cloudbeaver-admin`  | `CLOUDBEAVER_ADMIN_NAME`, `CLOUDBEAVER_ADMIN_PASSWORD`                   | CloudBeaver                |
| `grafana-admin`      | `GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`                           | Grafana                    |

`BUCKET_ADDRESS` gets `https://` in front when Doppler holds it without a scheme. The database password is not in Doppler: CloudNativePG creates it in the `medilab-db-app` Secret.

## Database

- The `medilab-db` `Cluster` runs one instance on the `local-path` storage of its node, with 20 GiB, and creates the `medilab` database owned by the `medilab` user.
- The instance requests one core and 3 GiB, with its memory limit equal to the request. Its parameters are sized for that memory on SSD storage: `shared_buffers` 768 MB, `effective_cache_size` 2 GB, `work_mem` 8 MB, `maintenance_work_mem` 256 MB, `random_page_cost` 1.1, `effective_io_concurrency` 200 and `max_wal_size` 2 GB, with 200 connections.
- The `backups` `ObjectStore` writes the WAL archive and the base backups to `s3://medilab-backups/postgres`, compressed, and keeps them for 30 days. The bucket endpoint reaches the plugin's sidecar as `AWS_ENDPOINT_URL`, since the object store can only take it as plain text. The sidecar sets `AWS_REQUEST_CHECKSUM_CALCULATION` and `AWS_RESPONSE_CHECKSUM_VALIDATION` to `when_required`, since the object storage refuses the checksums boto3 adds to multipart uploads by default.
- The `medilab-db-daily` `ScheduledBackup` takes a base backup every day at 02:00 Asia/Ho_Chi_Minh, written as `0 0 19 * * *` because the operator reads the schedule in UTC.

## Odoo

- `odoo.conf` comes from the `odoo-config` Secret, not the image: six workers, one cron thread, `proxy_mode`, no database manager and only the `medilab` database. Odoo reaches the database through the `medilab-db-rw` service with the user in `medilab-db-app`, with at most 8 connections per process.
- Odoo and the database together get 8 GiB: the Odoo pod requests three cores and 4 GiB with a 5 GiB limit, and each worker is recycled above 576 MiB and killed above 896 MiB, so every process fits the limit at its soft memory limit. A worker is also recycled after 8192 requests. The pod has no CPU limit, so it uses the node's idle cores.
- The upgrade Job requests three cores and 2 GiB with a 4 GiB limit, on top of those 8 GiB while it runs.
- With no outgoing mail server stored in Odoo and no Brevo settings in the environment, Odoo sends every e-mail to Mailpit on port 1025, without TLS.
- Odoo and the upgrade Job get the `medilab-filestore` bucket credentials and endpoint from the `filestore-bucket` Secret as `BUCKET_LABORATORY_*`, with `BUCKET_LABORATORY_NAME=medilab-filestore`, `BUCKET_LABORATORY_REGION=us-east-1` and `BUCKET_FILESTORE=1`. Attachments are kept in the bucket and cached in the pod's `/var/lib/odoo` `emptyDir` alongside the sessions; see [Laboratory files](../specs/laboratory-files.md#filestore).
- Traefik routes `lims.soltunemontepre.tech` to Odoo, and `/websocket` to its websocket port, and tells Odoo the request came over HTTPS.
- Every sync of the `odoo` application runs, in order:
  1. A `PreSync` hook: the `medilab-db-pre-sync` on-demand `Backup`, which must complete.
  2. A `Sync` hook: the `odoo-upgrade` Job. Its init container first upgrades `sol_inventory`, so that `stock` reloads under its current access rules. The Job then installs `sol_laboratory`, `sol_commerce`, `sol_inventory`, `sol_theme` and `sol_demo` when missing and upgrades every installed module. `MEDILAB_DEMO_PASSWORD` is not set, so the `demo.<role>` users keep the password `demo`. It does not retry; a failure fails the sync.
  3. The rolling update of the `odoo` Deployment, one replica at a time, with `maxSurge: 1`, `maxUnavailable: 0` and a `progressDeadlineSeconds` of 10 minutes.
- Each hook is replaced at the next sync, so the last backup and Job stay readable until then.

## Mailpit

- Mailpit receives every e-mail Odoo sends over SMTP and delivers none. It keeps the latest 5000 messages in a database on a 2 GiB `local-path` volume, and accepts any SMTP login.
- Traefik routes `mail.soltunemontepre.tech` to its web UI, which asks for the users in `MAILPIT_UI_AUTH`.

## CloudBeaver

- CloudBeaver 26.2.2 keeps the entire `/opt/cloudbeaver/workspace` on the existing 1 GiB `cloudbeaver-workspace` PVC: H2 at `.data/cb.h2v2.dat.mv.db`, runtime settings at `.data/.cloudbeaver.runtime.conf`, credential encryption material, accounts, projects and connections. Both H2 and completed runtime settings must survive. A healthy H2 connection alone does not establish completed setup. `Recreate` and one replica prevent concurrent H2 writers; the PVC has `Prune=false,Delete=false` in Argo CD. `local-path` remains tied to its node and needs a separate workspace backup; PostgreSQL backups do not contain it.
- On a pristine workspace, `bootstrap/start.sh` records a bootstrap attempt and lets CloudBeaver create the administrator from `cloudbeaver-admin`. The normalized identifier must differ from the built-in `admin` and `user` teams. Anonymous access defaults to off. The helper does not rename accounts or change the Secret. CloudBeaver writes completed runtime settings only after security setup succeeds.
- A workspace with a nonempty runtime `server.serverName` and the existing nonempty H2 file starts with bootstrap variables removed. This includes installations created before the startup guard existed. The application owns its runtime settings; Git does not supply a replacement `serverName` to bypass setup. The guard runs on every container start, including a restart within the same Pod.
- A bootstrap attempt without completed runtime settings may be interrupted setup or a later loss of completion state; the attempt marker alone cannot distinguish them. Audit an isolated backup clone before choosing recovery. H2, `.data` or `.metadata` without valid runtime settings is an existing workspace requiring recovery; its previous completion state is unknown. Both cases stop before the application starts. They require the reviewed [recovery procedure](../workflows/cloudbeaver-recovery.md), even if an administrator identifier in a Secret has been corrected. Runtime settings without H2 also stop, since silently creating an empty management database would lose accounts.
- The init container compiles the helpers with the JDK and Gson already shipped in the pinned CloudBeaver image. The generated ConfigMap's content hash changes the Pod template when the helpers change. The compiled classes and readiness session cookie live in `emptyDir`; installation state lives on the PVC.
- Connection provisioning adds `medilab-postgres` only when missing, preserving other connections, folders, unknown JSON properties, existing credential files and any existing definition of that ID. It backs up a changed JSON file, serializes credentials with Gson, writes atomically with mode `0600`, and never deletes credential files. New native authentication uses `userName` and `userPassword` from `medilab-db-app`. The seed can remain plaintext after connecting, so the workspace and all backups must remain access-controlled and encrypted at the backup destination. Verify authenticated credential-storage migration before assuming the seed has been removed; provisioning never forces it. Provisioning does not automatically rotate or repair existing connections: change their credentials through an authenticated, reviewed operation after backing up the workspace.
- Readiness requires persisted completion state and an HTTP 200 GraphQL response with boolean `serverConfig.configurationMode=false` and no `errors`. It rejects invalid JSON, missing data, redirects, connection errors and setup mode, and reuses its session cookie. TCP startup/liveness probes detect process availability separately. The Service does not publish unready endpoints, so Traefik routes `cloudbeaver.soltunemontepre.tech` only to initialized Pods; an incomplete installation has no usable backend. `/status` and `/` must not be used as initialization readiness checks.
- A GitOps rollout, workspace recovery or rollback requires the backup, validation and approval steps in [CloudBeaver recovery](../workflows/cloudbeaver-recovery.md). Keep the PVC name, storage class, mount and application version unchanged. Never repair this installation by deleting H2, completing the public wizard, editing a live Deployment or synchronizing Argo CD without review.

## Logs

- Alloy reads the logs of every pod through the Kubernetes API and sends them to Loki, labelled with `namespace`, `pod`, `container` and `app`. Odoo's lines also get their `level`, such as `INFO`, `WARNING` or `ERROR`, and its `/web/health` requests, which the probes make every few seconds, are dropped.
- Loki runs as one process and keeps the logs for 14 days on a 10 GiB `local-path` volume.
- Grafana has Loki as its data source and keeps its dashboards in a 1 GiB `local-path` volume. It asks for the administrator in the `grafana-admin` Secret; sign-up and anonymous access are off.
- Grafana loads the dashboards of the `grafana-dashboards` ConfigMap into the `MediLab` folder and does not let them be deleted or edited. Each dashboard is a JSON file in `infra/cluster/grafana-dashboards/`, listed in its `kustomization.yaml`.
- The **Odoo** dashboard reads the logs of `{app="odoo"}`, and `{app="odoo-upgrade"}` for the upgrade Job. It shows the requests by status, the log lines by level, the time of a request in Python and in the database, the queries per request, the busiest and slowest endpoints, the loggers behind the warnings and errors, the workers that reached a limit or timed out, and the logs, which a search box filters. It has no CPU, memory or restart panels, since the cluster keeps no metrics.
- Traefik routes `grafana.soltunemontepre.tech` to Grafana. Odoo's logs are under **Explore** with `{app="odoo"}`, and its errors with `{app="odoo", level="ERROR"}`.

## Ingress

`cloudflared` connects the remotely managed tunnel of `CLOUDFLARE_TUNNEL_TOKEN`. Terraform creates the tunnel and its public hostnames, which send every request to `http://traefik.kube-system.svc.cluster.local:80`.

- Only Cloudflare reaches the origin, so the `Cf-Connecting-IP` header Cloudflare sets is the client's address. Traefik binds no host port, the network policy `traefik-from-cloudflared` (Ansible's k3s role) lets only the `cloudflared` pods reach Traefik's web entry point, and `odoo-from-traefik` (`infra/cluster/odoo/network-policy.yaml`) lets only Traefik reach Odoo's web and websocket ports. k3s's network policy controller enforces both.
- The `odoo-rate-limit` middleware limits each client address, by `Cf-Connecting-IP`, on signing in to the laboratory files API (`/medilab/api/v1/sign-in`) and on the Brevo and PayOS webhooks: 30 requests a minute, with bursts of 30, then Traefik answers 429. Odoo also slows signing in per login; see [Laboratory files](../specs/laboratory-files.md#limits-on-signing-in).
- `tools/scripts/check_origin_isolation.sh` waits for the Odoo and Traefik rollouts to be healthy, then checks that a probe with the `cloudflared` label reaches Odoo's `/web/health` through Traefik, and that one with Traefik's label reaches Odoo directly. It then checks that a pod with neither label times out on both paths with forged `Cf-Connecting-IP` and `X-Forwarded-For` headers. A Job owns each probe pod so application ReplicaSets cannot adopt it. The check removes its Jobs on exit and gives them a deadline and an expiry in case it is interrupted. An unavailable origin, a DNS error or a probe that cannot run fails the check.

## Related documents

- [Architecture](architecture.md)
- [Provisioning](provisioning.md)
- [Pipelines](pipelines.md)
- [Secrets](secrets.md)
