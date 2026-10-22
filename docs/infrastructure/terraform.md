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

- `lims.soltunemontepre.tech` is the only web host name; add one by adding it to `web_hostnames` in `infra/dns.tf`, which creates its record and its public hostname together.
- The tunnel's token is the sensitive output `tunnel_token`. Terraform does not store it in Doppler; see `CLOUDFLARE_TUNNEL_TOKEN` in [Secrets](secrets.md).
- Deleting a host name from `web_hostnames` and applying removes its record and its public hostname.

## GitHub

The `github` module publishes the Actions secrets and creates the `ansible` and `ansible-apply` environments; see [Secrets](secrets.md#published-to-github) and [Pipelines](pipelines.md#cd-ansible).

## Related documents

- [Architecture](architecture.md)
- [Secrets](secrets.md)
- [Pipelines](pipelines.md)
- [Terraform conventions](../conventions/terraform.md)
