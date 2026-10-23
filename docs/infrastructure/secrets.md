# Secrets

Doppler is the only store for credentials. Terraform in `infra/` reads the `dev` config and publishes secrets to the GitHub repository's Actions secrets.

## Local development

`task doppler` logs the Doppler CLI in and selects `medilab` `dev` for the repository. The login is stored by the CLI, so nothing is written to the shell or the user environment, and the same steps work on Windows, Linux and macOS.

Every local program that needs a secret is started through `doppler run --project medilab --config dev -- <program>`: the `task tf:*` commands, and the `doppler`, `sonarqube` and `context7` MCP servers in `.mcp.json`. `doppler run` injects the secrets of `dev`, including `DOPPLER_TOKEN`, into that program only.

## Doppler config

| Project   | Config  | Contains                                                                                                                                                                                                                                                                                                                                                                     | Read by                                                                         |
| --------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `medilab` | `dev`   | `ARM_CLIENT_ID`, `ARM_CLIENT_SECRET`, `ARM_SUBSCRIPTION_ID`, `ARM_TENANT_ID`, `ARGOCD_AUTH_TOKEN`, `CLOUDFLARE_API_TOKEN`, `CONTEXT7_TOKEN`, `DOPPLER_INFRA_TOKEN`, `DOPPLER_TOKEN`, `GITHUB_TOKEN`, `RELEASE_APP_ID`, `RELEASE_APP_PRIVATE_KEY`, `SONARQUBE_TOKEN`, `TERRAFORM_TOKEN`                                                                                       | every `task tf:*`, the pipelines and the MCP servers                            |
| `medilab` | `infra` | `ANSIBLE_SSH_PRIVATE_KEY`, `BUCKET_ADDRESS`, `BUCKET_BACKUP_ACCESS_KEY`, `BUCKET_BACKUP_SECRET_KEY`, `BUCKET_MAIN_ACCESS_KEY`, `BUCKET_MAIN_SECRET_KEY`, `CLOUDBEAVER_ADMIN_NAME`, `CLOUDBEAVER_ADMIN_PASSWORD`, `CLOUDFLARE_TUNNEL_TOKEN`, `CLUSTER_DOPPLER_TOKEN`, `K3S_TOKEN`, `MAILPIT_UI_AUTH`, `NODE_A_PUBLIC_ADDRESS`, `NODE_B_PUBLIC_ADDRESS`, `ODOO_ADMIN_PASSWORD` | `cd-ansible`, the `task ansible:*` commands and External Secrets in the cluster |

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
- `CLOUDBEAVER_ADMIN_NAME` and `CLOUDBEAVER_ADMIN_PASSWORD` are the CloudBeaver administrator, created on its first start. The password needs at least eight characters in mixed case.
- `MAILPIT_UI_AUTH` holds the logins of the Mailpit web UI, each written as `user:password` and separated by spaces.
- Every token has the least access it needs, an expiry, and is entered through a prompt or a pipe, never printed or pasted into chat.

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

| Environment secret    | Environments               | Doppler source        |
| --------------------- | -------------------------- | --------------------- |
| `DOPPLER_INFRA_TOKEN` | `ansible`, `ansible-apply` | `DOPPLER_INFRA_TOKEN` |

Terraform owns these secrets: a value edited in GitHub is overwritten on the next `task tf:apply`. To change one, edit it in Doppler and apply. `DOPPLER_INFRA_TOKEN` must exist in `dev` before Terraform reads it, including in the `ci-infra` plan of the pull request that adds it.

## Pipelines

- `ci-infra` and `cd-infra`, described in [Pipelines](pipelines.md), read the `dev` config through the `DOPPLER_TOKEN` Actions secret, a Doppler service token with read access to `dev`. Terraform publishes it; the first run that creates it needs the value in the Actions secrets already, so set it by hand once to bootstrap the pipelines.
- `cd-ansible` reads the `infra` config through the `DOPPLER_INFRA_TOKEN` secret of the `ansible` and `ansible-apply` environments, which only `main` can use; see [Pipelines](pipelines.md#cd-ansible).

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
