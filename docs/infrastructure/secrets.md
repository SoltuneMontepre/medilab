# Secrets

Doppler is the only store for credentials. Terraform in `infra/` reads the `tf` config and publishes secrets to the GitHub repository's Actions secrets.

## Doppler config

| Project   | Config | Contains                                      | Read by           |
| --------- | ------ | --------------------------------------------- | ----------------- |
| `medilab` | `tf`   | `DOPPLER_TOKEN`, `GITHUB_TOKEN`, `SONAR_TOKEN` | every `task tf:*` |

- Seed `tf` by hand; Terraform cannot create the config it reads.
- `DOPPLER_TOKEN` is the token Terraform's Doppler provider authenticates with. It needs read access to `tf`.
- `GITHUB_TOKEN` needs permission to write Actions secrets on the repository.

## Published to GitHub

| Actions secret | Doppler source |
| -------------- | -------------- |
| `SONAR_TOKEN`  | `SONAR_TOKEN`  |

Terraform owns these secrets: a value edited in GitHub is overwritten on the next `task tf:apply`. To change one, edit it in Doppler and apply.

## Pipelines

- `ci-infra` runs `terraform fmt`, `validate` and `plan` on pull requests that change `infra/`.
- `cd-infra` runs `terraform apply` when `infra/` changes on `main`.
- Both read the `tf` config through the `DOPPLER_TOKEN` Actions secret, a Doppler service token with read access to `tf`. Set it by hand once; Terraform does not publish it.

## Commands

See [Taskfiles](../conventions/taskfiles.md): `task tf:setup` once, then `task tf:plan` and `task tf:apply`.

## State

State is stored in the HCP Terraform workspace `medilab` of the organization `soltunemontepre_devops`, since it holds the published secret values. The workspace execution mode is Local, so runs stay on the developer machine and in the pipelines with the Doppler secrets.

- Developers authenticate with `terraform login`.
- The pipelines authenticate with the `TF_API_TOKEN` Actions secret, an HCP Terraform team token with write access to the workspace. Set it by hand once; Terraform does not publish it.

## Related documents

- [Taskfiles](../conventions/taskfiles.md)
