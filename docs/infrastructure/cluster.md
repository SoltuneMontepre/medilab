# Cluster

What Argo CD deploys from `infra/cluster/` onto the cluster in [Architecture](architecture.md), once Ansible has installed k3s and Argo CD; see [Provisioning](provisioning.md).

## Layout

`infra/cluster/` is the path of the `medilab` root application. Its `kustomization.yaml` lists one Argo CD `Application` per component, in `infra/cluster/applications/`:

| Application           | Deploys                                                                    | Source                       | Namespace          | Wave |
| --------------------- | -------------------------------------------------------------------------- | ---------------------------- | ------------------ | ---- |
| `cert-manager`        | cert-manager, which issues the TLS certificates of the Barman Cloud plugin | `cert-manager` chart         | `cert-manager`     | -3   |
| `external-secrets`    | External Secrets Operator                                                  | `external-secrets` chart     | `external-secrets` | -3   |
| `csi-s3`              | The S3 CSI driver, with the GeeseFS mounter                                | `csi-s3` chart               | `csi-s3`           | -3   |
| `secret-store`        | The `doppler` `ClusterSecretStore`                                         | `infra/cluster/secret-store` | `external-secrets` | -2   |
| `cloudnative-pg`      | The CloudNativePG operator                                                 | `cloudnative-pg` chart       | `cnpg-system`      | -2   |
| `plugin-barman-cloud` | The Barman Cloud plugin of CloudNativePG                                   | `plugin-barman-cloud` chart  | `cnpg-system`      | -1   |
| `database`            | The Postgres `Cluster`, its object store and its scheduled backup          | `infra/cluster/database`     | `medilab`          | 0    |
| `cloudflared`         | The Cloudflare Tunnel connector                                            | `infra/cluster/cloudflared`  | `medilab`          | 1    |
| `odoo`                | Odoo, its filestore volume, the pre-sync backup and the upgrade Job        | `infra/cluster/odoo`         | `medilab`          | 1    |

- The root application syncs the applications wave by wave and waits until every application of a wave is healthy before the next. Argo CD has no health check for an `Application` by default; the `argocd` role adds one.
- Every application syncs automatically, prunes what was removed from Git and reverts changes made by hand. Every application except `odoo` retries a failed sync five times, so the first install settles while operators and their CRDs come up.
- The `database` application never prunes or deletes the `Cluster`, even when it is removed from Git.

## Versions

Every chart and image is pinned and upgraded by changing it in `infra/cluster/`:

| What                      | Version  | Where                                   |
| ------------------------- | -------- | --------------------------------------- |
| cert-manager chart        | v1.21.2  | `applications/cert-manager.yaml`        |
| External Secrets chart    | 2.13.0   | `applications/external-secrets.yaml`    |
| S3 CSI driver chart       | 0.43.7   | `applications/csi-s3.yaml`              |
| CloudNativePG chart       | 0.29.1   | `applications/cloudnative-pg.yaml`      |
| Barman Cloud plugin chart | 0.8.1    | `applications/plugin-barman-cloud.yaml` |
| Postgres image            | 18.4     | `imageName` in `database/cluster.yaml`  |
| `cloudflared` image       | 2026.9.3 | `cloudflared/deployment.yaml`           |
| MediLab image             | released | `newTag` in `odoo/kustomization.yaml`   |

`cd-core` releases the MediLab image by committing its tag to `newTag`; see [Pipelines](pipelines.md#cd-core).

## Secrets

External Secrets reads the Doppler `infra` config through the `doppler` `ClusterSecretStore`, with the service token that Ansible stores in the `doppler-token` Secret of the `external-secrets` namespace. Each component gets its own Secret, refreshed every hour:

| Secret               | Doppler secrets                                                          | Used by                    |
| -------------------- | ------------------------------------------------------------------------ | -------------------------- |
| `backup-bucket`      | `BUCKET_ADDRESS`, `BUCKET_BACKUP_ACCESS_KEY`, `BUCKET_BACKUP_SECRET_KEY` | The `backups` object store |
| `filestore-bucket`   | `BUCKET_ADDRESS`, `BUCKET_MAIN_ACCESS_KEY`, `BUCKET_MAIN_SECRET_KEY`     | The filestore volume       |
| `cloudflared-tunnel` | `CLOUDFLARE_TUNNEL_TOKEN`                                                | `cloudflared`              |
| `odoo-config`        | `ODOO_ADMIN_PASSWORD`, written into `odoo.conf`                          | Odoo and the upgrade Job   |

`BUCKET_ADDRESS` gets `https://` in front when Doppler holds it without a scheme. The database password is not in Doppler: CloudNativePG creates it in the `medilab-db-app` Secret.

## Database

- The `medilab-db` `Cluster` runs one instance on the `local-path` storage of its node, with 20 GiB, and creates the `medilab` database owned by the `medilab` user.
- The `backups` `ObjectStore` writes the WAL archive and the base backups to `s3://medilab-backups/postgres`, compressed, and keeps them for 30 days. The bucket endpoint reaches the plugin's sidecar as `AWS_ENDPOINT_URL`, since the object store can only take it as plain text. The sidecar sets `AWS_REQUEST_CHECKSUM_CALCULATION` and `AWS_RESPONSE_CHECKSUM_VALIDATION` to `when_required`, since the provider refuses the checksums boto3 adds to multipart uploads by default.
- The `medilab-db-daily` `ScheduledBackup` takes a base backup every day at 02:00 Asia/Ho_Chi_Minh, written as `0 0 19 * * *` because the operator reads the schedule in UTC.

## Odoo

- `odoo.conf` comes from the `odoo-config` Secret, not the image: four workers, one cron thread, `proxy_mode`, no database manager and only the `medilab` database. Odoo reaches the database through the `medilab-db-rw` service with the user in `medilab-db-app`.
- The filestore bucket is mounted at `/var/lib/odoo/filestore` through the `medilab-filestore` volume, so every replica and the upgrade Job see the same attachments. The rest of `/var/lib/odoo`, including the sessions, is local to each pod.
- Traefik routes `lims.soltunemontepre.tech` to Odoo, and `/websocket` to its websocket port, and tells Odoo the request came over HTTPS.
- Every sync of the `odoo` application runs, in order:
  1. A `PreSync` hook: the `medilab-db-pre-sync` on-demand `Backup`, which must complete.
  2. A `Sync` hook: the `odoo-upgrade` Job, which installs `sol_laboratory`, `sol_commerce`, `sol_inventory` and `sol_theme` when missing and upgrades every installed module. It does not retry; a failure fails the sync.
  3. The rolling update of the `odoo` Deployment, one replica at a time, with `maxSurge: 1`, `maxUnavailable: 0` and a `progressDeadlineSeconds` of 10 minutes.
- Each hook is replaced at the next sync, so the last backup and Job stay readable until then.

## Ingress

`cloudflared` connects the remotely managed tunnel of `CLOUDFLARE_TUNNEL_TOKEN`. Terraform creates the tunnel and its public hostnames, which send every request to `http://traefik.kube-system.svc.cluster.local:80`.

## Related documents

- [Architecture](architecture.md)
- [Provisioning](provisioning.md)
- [Pipelines](pipelines.md)
- [Secrets](secrets.md)
