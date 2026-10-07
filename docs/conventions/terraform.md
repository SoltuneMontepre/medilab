# Terraform conventions

How the Terraform code in `infra/` is written and kept reproducible.

## Providers

- Pin every provider to an exact version in `infra/terraform.tf`.
- We do not tolerate deprecation warnings in the pipelines. If a provider version is deprecated, upgrade it and pin the new version.

## Secrets

- Terraform reads secret values from Doppler and never from files or defaults.
- The Actions secret name and its Doppler name may differ; the table in [Secrets](../infrastructure/secrets.md) is the mapping.

## Related documents

- [Secrets](../infrastructure/secrets.md)
- [Taskfiles](taskfiles.md)
