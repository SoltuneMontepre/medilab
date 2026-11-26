# Terraform

What the Terraform code in `infra/` creates. How it is written is in [Terraform conventions](../conventions/terraform.md), and how it authenticates in [Secrets](secrets.md).

## Cloudflare

Terraform manages the `soltunemontepre.tech` zone's records and the tunnel that carries web traffic; see [Architecture](architecture.md#ingress).

| Resource         | Created by       | What it is                                                                                            |
| ---------------- | ---------------- | ----------------------------------------------------------------------------------------------------- |
| Tunnel `medilab` | `modules/tunnel` | A remotely managed tunnel that `cloudflared` connects with its token                                  |
| Public hostnames | `modules/tunnel` | One per web host name, each sending its requests to `http://traefik.kube-system.svc.cluster.local:80` |
| Fallback         | `modules/tunnel` | Any other host name on the tunnel gets a 404                                                          |
| Web DNS records  | `modules/dns`    | A proxied CNAME per web host name to `<tunnel-id>.cfargotunnel.com`                                   |

- The web host names are `lims.soltunemontepre.tech`, `argocd.soltunemontepre.tech`, `mail.soltunemontepre.tech`, `cloudbeaver.soltunemontepre.tech`, `grafana.soltunemontepre.tech` and `office.soltunemontepre.tech`; add one by adding it to `web_hostnames` in `infra/dns.tf`, which creates its record and its public hostname together.
- The tunnel's token is the sensitive output `tunnel_token`. Terraform does not store it in Doppler; see `CLOUDFLARE_TUNNEL_TOKEN` in [Secrets](secrets.md).
- Deleting a host name from `web_hostnames` and applying removes its record and its public hostname.

Terraform also creates the `medilab-release` R2 bucket, from which phones download Medilab Mobile; see [cd-mobile-app](pipelines.md#cd-mobile-app).

| Resource                  | Created by          | What it is                                                                              |
| ------------------------- | ------------------- | --------------------------------------------------------------------------------------- |
| Bucket `medilab-release`  | `modules/r2_bucket` | A Standard R2 bucket in the `apac` location                                             |
| Custom domain of a bucket | `modules/r2_bucket` | `release.soltunemontepre.tech`, which serves the bucket's objects publicly over TLS 1.2 |

- R2 creates and owns the custom domain's DNS record, so it is not in `modules/dns`.
- The bucket's public address is the output `release_bucket_public_address`; enter it in Doppler as `RELEASE_BUCKET_PUBLIC_ADDRESS`, see [Secrets](secrets.md).
- The R2 API token that `cd-mobile-app` uploads with is created by hand; see `AWS_ACCESS_KEY_ID` in [Secrets](secrets.md).

## GitHub

The `github` module publishes the Actions secrets and variables, creates the `ansible`, `ansible-apply` and `database-reset` environments, which only `main` may use, and the `mobile-release` environment, which only `mobile-v*` tags may use, each with the Doppler token it names, manages the `main` ruleset, which requires a reviewed pull request and the checks in `required_checks` and lets organization admins and the release GitHub App bypass it. The `release` variable sets the `RELEASE_MODE`, `RELEASE_DAYS` and `RELEASE_HOURS` Actions variables of [cd-core](pipelines.md#cd-core); see [Secrets](secrets.md#published-to-github) and [Pipelines](pipelines.md#cd-ansible).

## Related documents

- [Architecture](architecture.md)
- [Secrets](secrets.md)
- [Pipelines](pipelines.md)
- [Terraform conventions](../conventions/terraform.md)
