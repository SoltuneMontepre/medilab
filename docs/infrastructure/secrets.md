# Secrets

Doppler is the source of truth for shared development and deployment credentials. Terraform in `infra/` reads the `dev` config and publishes secrets to the GitHub repository's Actions secrets. Isolated local credentials and a user's Sync credentials have the separate ownership described below.

## Local development

`task doppler` logs the Doppler CLI in and selects `medilab` `dev` for the repository. The login is stored by the CLI, so nothing is written to the shell or the user environment, and the same steps work on Windows, Linux and macOS.

Programs that need shared credentials start through `doppler run --project medilab --config dev -- <program>`: the `task tf:*` commands, and the `doppler`, `sonarqube` and `context7` MCP servers in `.mcp.json`. `doppler run` injects the secrets of `dev`, including `DOPPLER_TOKEN`, into that program only.

`task setup` in an empty worktree creates an isolated demo without Doppler or inherited application credentials. Managed local ONLYOFFICE generates its own JWT and private certificate authority beneath the ignored `.local/onlyoffice` directory, protected by private filesystem permissions or Windows ACLs. The public CA is mounted only where the owned containers need it; setup does not change the host trust store. Preserve this material with its owned persistent state across reruns and recovery. Do not copy it into deployment configs, Git, logs or chat. See [local setup](../workflows/setting-up.md#local-demo-setup).

The native Sync app uses the operating system credential store for each user's API credential; its existing explicitly enabled file-fallback policy remains unchanged. Setup neither imports that credential from Doppler nor changes the installed app's profile or keyring. Development endpoint metadata contains no API credential. Use an isolated OS account or verified private credential-store session for desktop acceptance tests.

The only credential a Claude Code cloud environment holds is `DOPPLER_TOKEN`, an environment variable that `task ai:env` writes to `.local/cloud.env` for pasting into its settings; `doppler run` reads the other secrets through it. See [Working in a cloud session](../workflows/cloud-session.md).

## Doppler config

| Project   | Config  | Contains                                                                                                                                                                                                                                                                                                                                                                                                                     | Read by                                                                         |
| --------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `medilab` | `dev`   | `ARM_CLIENT_ID`, `ARM_CLIENT_SECRET`, `ARM_SUBSCRIPTION_ID`, `ARM_TENANT_ID`, `ARGOCD_AUTH_TOKEN`, `CLOUDFLARE_API_TOKEN`, `CONTEXT7_TOKEN`, `DOPPLER_INFRA_TOKEN`, `DOPPLER_TOKEN`, `GITHUB_TOKEN`, `RELEASE_APP_ID`, `RELEASE_APP_PRIVATE_KEY`, `SONARQUBE_TOKEN`, `TERRAFORM_TOKEN`                                                                                                                                       | every `task tf:*`, the pipelines and the MCP servers                            |
| `medilab` | `infra` | `ANSIBLE_SSH_PRIVATE_KEY`, `BUCKET_ADDRESS`, `BUCKET_BACKUP_ACCESS_KEY`, `BUCKET_BACKUP_SECRET_KEY`, `BUCKET_MAIN_ACCESS_KEY`, `BUCKET_MAIN_SECRET_KEY`, `CLOUDBEAVER_ADMIN_NAME`, `CLOUDBEAVER_ADMIN_PASSWORD`, `CLOUDFLARE_TUNNEL_TOKEN`, `CLUSTER_DOPPLER_TOKEN`, `GRAFANA_ADMIN_PASSWORD`, `GRAFANA_ADMIN_USER`, `K3S_TOKEN`, `MAILPIT_UI_AUTH`, `NODE_A_PUBLIC_ADDRESS`, `NODE_B_PUBLIC_ADDRESS`, `ODOO_ADMIN_PASSWORD` | `cd-ansible`, the `task ansible:*` commands and External Secrets in the cluster |

- Seed `dev` and `infra` by hand; Terraform cannot create the config it reads.
- Set `TF_VAR_doppler_config=<config>` to read another config.
- `DOPPLER_TOKEN` is read from the environment by Terraform's Doppler provider: injected by `doppler run` on a developer machine, the Actions secret in the pipelines. It needs read access to the config being read.
- `DOPPLER_INFRA_TOKEN` is a Doppler service token with read access to `infra` only, published to the Ansible environments for `cd-ansible`.
- `GITHUB_TOKEN` needs permission to write Actions secrets, variables, environments and administration on the repository.
- `RELEASE_APP_ID` and `RELEASE_APP_PRIVATE_KEY` are the ID and a private key of the release GitHub App, which an organization owner creates under the organization's Developer settings with Contents and Pull requests read and write and no webhook, and installs on this repository only.
- `ARM_CLIENT_ID`, `ARM_CLIENT_SECRET`, `ARM_SUBSCRIPTION_ID` and `ARM_TENANT_ID` are a service principal of the Azure for Students subscription, read from the environment by Terraform's `azurerm` provider to manage the witness VM. The principal has the Contributor role on the witness resource group only.
- `ARGOCD_AUTH_TOKEN` is a token of the Argo CD `release` account, used by `cd-core` to check a release. Create it after the `argocd` role has run, logged in to Argo CD as `admin`: `argocd account generate-token --account release`.
- `CLOUDFLARE_API_TOKEN` is read from the environment by Terraform's Cloudflare provider. It edits DNS and the tunnel of the `soltunemontepre.tech` zone and creates Origin CA certificates: Zone read and DNS edit on the zone, Cloudflare Tunnel edit on the account.
- `CONTEXT7_TOKEN` is a Context7 API key, read by the `context7` MCP server.
- `TERRAFORM_TOKEN` is an HCP Terraform team token with write access to the workspace.
- `ANSIBLE_SSH_PRIVATE_KEY` is the private key of the `ansible` user on every node; see [Provisioning a node](../workflows/provisioning-node.md).
- `K3S_TOKEN` is the k3s cluster token. It is set once: joining nodes and etcd snapshot restores need the same value.
- `BUCKET_ADDRESS` is the endpoint of the object storage. `BUCKET_MAIN_ACCESS_KEY` and `BUCKET_MAIN_SECRET_KEY` reach the `medilab-filestore` bucket; `BUCKET_BACKUP_ACCESS_KEY` and `BUCKET_BACKUP_SECRET_KEY` reach the `medilab-backups` bucket.
- `NODE_A_PUBLIC_ADDRESS` and `NODE_B_PUBLIC_ADDRESS` are the public IPs of Server A and Server B, the addresses Ansible connects to.
- `CLUSTER_DOPPLER_TOKEN` is a Doppler service token with read access to `infra`. Ansible stores it in the cluster as the `doppler-token` Secret, through which External Secrets reads the secrets below; see [Cluster](cluster.md#secrets).
- `CLOUDFLARE_TUNNEL_TOKEN` is the token of the Cloudflare Tunnel that `cloudflared` connects. Terraform creates the tunnel; after `task tf:apply`, pipe `terraform -chdir=infra output -raw tunnel_token` to the clipboard and enter it in Doppler by hand, since the pipelines' token cannot write to `infra`.
- `ODOO_ADMIN_PASSWORD` is Odoo's master password, written into the production `odoo.conf`.
- `CLOUDBEAVER_ADMIN_NAME` and `CLOUDBEAVER_ADMIN_PASSWORD` bootstrap CloudBeaver only on a pristine workspace. The normalized name must differ from the built-in teams `admin` and `user`. The password needs at least eight characters in mixed case. Changing these values does not rename an existing administrator, recover missing runtime settings or rotate an existing account's password. Readiness separately uses `CB_VERIFY_NAME` and `CB_VERIFY_PASSWORD`, initially referencing these same Secret keys. They must identify a working existing administrator. If bootstrap values are stale, prove the correct credential source on a backup clone and review alternate Secret references in Git; never reset an existing account merely to satisfy a probe. Failed probe authentication is latched until application restart; investigate before approving that restart. See [CloudBeaver recovery](../workflows/cloudbeaver-recovery.md).
- `GRAFANA_ADMIN_USER` and `GRAFANA_ADMIN_PASSWORD` are the Grafana administrator.
- `MAILPIT_UI_AUTH` holds the logins of the Mailpit web UI, each written as `user:password` and separated by spaces.
- Every token has the least access it needs, an expiry, and is entered through a prompt or a pipe, never printed or pasted into chat.

## ONLYOFFICE

Before enabling deployed online editing, seed `ONLYOFFICE_JWT_SECRET` in `infra` with at least 32 random base64url characters. The candidate `onlyoffice-jwt` ExternalSecret shares its `jwt-secret` key with Document Server and Odoo. Rotation needs a coordinated drained rollout; no secret value enters Git or logs. `ONLYOFFICE_ALERT_WEBHOOK` separately reaches Grafana through the candidate `onlyoffice-alerting` ExternalSecret in `monitoring`, after operator routing is selected. Internal TLS is issued by cert-manager; clients receive only its public CA. The [ONLYOFFICE runbook](onlyoffice.md) defines the deployment and licence gates.

## Published to GitHub

| Actions secret            | Doppler source            |
| ------------------------- | ------------------------- |
| `SONAR_TOKEN`             | `SONARQUBE_TOKEN`         |
| `DOPPLER_TOKEN`           | `DOPPLER_TOKEN`           |
| `TF_API_TOKEN`            | `TERRAFORM_TOKEN`         |
| `ARGOCD_AUTH_TOKEN`       | `ARGOCD_AUTH_TOKEN`       |
| `RELEASE_APP_ID`          | `RELEASE_APP_ID`          |
| `RELEASE_APP_PRIVATE_KEY` | `RELEASE_APP_PRIVATE_KEY` |

The `ARGOCD_SERVER` Actions variable holds `argocd.soltunemontepre.tech`.

| Environment secret    | Environments                                 | Doppler source        |
| --------------------- | -------------------------------------------- | --------------------- |
| `DOPPLER_INFRA_TOKEN` | `ansible`, `ansible-apply`, `database-reset` | `DOPPLER_INFRA_TOKEN` |

Terraform owns these secrets: a value edited in GitHub is overwritten on the next `task tf:apply`. To change one, edit it in Doppler and apply. `DOPPLER_INFRA_TOKEN` must exist in `dev` before Terraform reads it, including in the `ci-infra` plan of the pull request that adds it.

## Pipelines

- `ci-infra` and `cd-infra`, described in [Pipelines](pipelines.md), read the `dev` config through the `DOPPLER_TOKEN` Actions secret, a Doppler service token with read access to `dev`. Terraform publishes it; the first run that creates it needs the value in the Actions secrets already, so set it by hand once to bootstrap the pipelines.
- `cd-ansible` and `cd-reset` read the `infra` config through the `DOPPLER_INFRA_TOKEN` secret of the `ansible`, `ansible-apply` and `database-reset` environments, which only `main` can use; see [Pipelines](pipelines.md#cd-ansible).

## Commands

See [Taskfiles](../conventions/taskfiles.md): `task doppler` once to log in, `task tf:setup` once, then `task tf:plan` and `task tf:apply`.

## State

State is stored in the HCP Terraform workspace `medilab` of the organization `soltunemontepre_devops`, since it holds the published secret values. The workspace execution mode is Local, so runs stay on the developer machine and in the pipelines with the Doppler secrets.

- Developers authenticate with `terraform login`.
- The pipelines authenticate with the `TF_API_TOKEN` Actions secret, an HCP Terraform team token with write access to the workspace. Terraform publishes it; set it by hand once to bootstrap the pipelines.

## Related documents

- [Provisioning](provisioning.md)
- [Cluster](cluster.md)
- [Taskfiles](../conventions/taskfiles.md)
- [Terraform](../conventions/terraform.md)
