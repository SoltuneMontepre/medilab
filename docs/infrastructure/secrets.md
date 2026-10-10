# Secrets

Doppler is the only store for credentials. Terraform in `infra/` reads the `dev` config and publishes secrets to the GitHub repository's Actions secrets.

## Local development

`task doppler` logs the Doppler CLI in and selects `medilab` `dev` for the repository. The login is stored by the CLI, so nothing is written to the shell or the user environment, and the same steps work on Windows, Linux and macOS.

Every local program that needs a secret is started through `doppler run --project medilab --config dev -- <program>`: the `task tf:*` commands, and the `doppler`, `sonarqube` and `context7` MCP servers in `.mcp.json`. `doppler run` injects the secrets of `dev`, including `DOPPLER_TOKEN`, into that program only.

## Doppler config

| Project   | Config | Contains                                                                                | Read by                                              |
| --------- | ------ | --------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| `medilab` | `dev`  | `CONTEXT7_TOKEN`, `DOPPLER_TOKEN`, `GITHUB_TOKEN`, `SONARQUBE_TOKEN`, `TERRAFORM_TOKEN` | every `task tf:*`, the pipelines and the MCP servers |

- Seed `dev` by hand; Terraform cannot create the config it reads.
- Set `TF_VAR_doppler_config=<config>` to read another config.
- `DOPPLER_TOKEN` is read from the environment by Terraform's Doppler provider: injected by `doppler run` on a developer machine, the Actions secret in the pipelines. It needs read access to the config being read.
- `GITHUB_TOKEN` needs permission to write Actions secrets on the repository.
- `CONTEXT7_TOKEN` is a Context7 API key, read by the `context7` MCP server.
- `TERRAFORM_TOKEN` is an HCP Terraform team token with write access to the workspace.
- Every token has the least access it needs, an expiry, and is entered through a prompt or a pipe, never printed or pasted into chat.

## Published to GitHub

| Actions secret  | Doppler source    |
| --------------- | ----------------- |
| `SONAR_TOKEN`   | `SONARQUBE_TOKEN` |
| `DOPPLER_TOKEN` | `DOPPLER_TOKEN`   |
| `TF_API_TOKEN`  | `TERRAFORM_TOKEN` |

Terraform owns these secrets: a value edited in GitHub is overwritten on the next `task tf:apply`. To change one, edit it in Doppler and apply.

## Pipelines

- `ci-infra` and `cd-infra`, described in [Pipelines](pipelines.md), read the `dev` config through the `DOPPLER_TOKEN` Actions secret, a Doppler service token with read access to `dev`. Terraform publishes it; the first run that creates it needs the value in the Actions secrets already, so set it by hand once to bootstrap the pipelines.

## Commands

See [Taskfiles](../conventions/taskfiles.md): `task doppler` once to log in, `task tf:setup` once, then `task tf:plan` and `task tf:apply`.

## State

State is stored in the HCP Terraform workspace `medilab` of the organization `soltunemontepre_devops`, since it holds the published secret values. The workspace execution mode is Local, so runs stay on the developer machine and in the pipelines with the Doppler secrets.

- Developers authenticate with `terraform login`.
- The pipelines authenticate with the `TF_API_TOKEN` Actions secret, an HCP Terraform team token with write access to the workspace. Terraform publishes it; set it by hand once to bootstrap the pipelines.

## Related documents

- [Taskfiles](../conventions/taskfiles.md)
- [Terraform](../conventions/terraform.md)
