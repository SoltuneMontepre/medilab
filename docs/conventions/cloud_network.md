# Cloud network

How scripts, Dockerfiles and tools are written so they work in a Claude Code cloud session, where every outbound connection goes through the session's proxy. Setting up and using a session is in [Working in a cloud session](../workflows/cloud-session.md).

## The proxy

| Behaviour                                                                                                  | Rule                                                                                                                       |
| ---------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| A host outside the environment's Allowed domains gets `403` on `CONNECT`                                   | List every host a script needs in the Allowed domains of [the setup](../workflows/cloud-session.md#set-up-the-environment) |
| Plain HTTP gets `405 Method Not Allowed`                                                                   | Use HTTPS URLs, including `apt` sources: switch `http://` to `https://` in `/etc/apt/sources.list.d/*.sources`             |
| HTTPS is re-signed with the proxy's certificate, `/root/.ccr/ca-bundle.crt`                                | A tool in a container trusts that bundle; it already holds the public roots, so it can replace the system bundle           |
| The proxy listens on `127.0.0.1`, given in `HTTPS_PROXY`                                                   | A container reaches it only with `--network host`                                                                          |
| `curl ... \| sh` installers are refused                                                                    | Install tools from package registries: `uv tool install`, `npm`, signed `apt` repositories                                 |
| `curl -sS "$HTTPS_PROXY/__agentproxy/status"` lists the recently refused hosts under `recentRelayFailures` | Check it first when a download fails                                                                                       |

## Hosts

| Host                                        | Reached by default | Used for                                     | Without it                                                                                                      |
| ------------------------------------------- | ------------------ | -------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `pypi.org`, `files.pythonhosted.org`        | Yes                | `uv` packages and tools such as `task`       |                                                                                                                 |
| `registry.npmjs.org`                        | Yes                | `npx` tools                                  |                                                                                                                 |
| `mirror.gcr.io`                             | Yes                | Docker Hub images, through the Docker mirror |                                                                                                                 |
| `archive.ubuntu.com`, `security.ubuntu.com` | Yes, over HTTPS    | `apt` in the Odoo base image                 |                                                                                                                 |
| `github.com` over Git                       | Yes                | Clone, fetch and push                        |                                                                                                                 |
| `ghcr.io`                                   | Yes                | Registry API of `MEDILAB_ODOO_IMAGE`         |                                                                                                                 |
| `pkg-containers.githubusercontent.com`      | No                 | Layers of `ghcr.io` images                   | `MEDILAB_ODOO_IMAGE` and `COPY --from=ghcr.io/...` fail to pull, so `task up` cannot start Odoo                 |
| `packages.doppler.com`                      | No                 | Doppler CLI `apt` key and packages           | The Doppler CLI is not installed                                                                                |
| `api.doppler.com`                           | No                 | Secrets read through `DOPPLER_TOKEN`         | `doppler run` fails; the `doppler`, `sonarqube` and `context7` MCP servers do not connect. `task up` still runs |

GitHub release downloads and `cli.doppler.com` are refused as well; do not rely on them.

## Docker builds

- Pass the proxy to the build with its value and declare it in the Dockerfile: `--build-arg HTTPS_PROXY="$HTTPS_PROXY"` with `ARG HTTPS_PROXY`.
- Give the proxy's certificate as a build secret, never with `COPY`, so it stays out of the image: `--secret id=proxy_ca,src=/root/.ccr/ca-bundle.crt` and `RUN --mount=type=secret,id=proxy_ca,mode=0444`.
- Mount the secret with `mode=0444`. A secret is readable only by root by default, and `apt` downloads as its `_apt` user, so it fails with "does not have a Release file". Point `apt` at it with `-o Acquire::https::CaInfo=/run/secrets/proxy_ca` and `uv` with `SSL_CERT_FILE=/run/secrets/proxy_ca`.
- Base images come from Docker Hub, which the mirror serves. A base or `COPY --from` image on `ghcr.io` needs `pkg-containers.githubusercontent.com`.

## Setup script

- The setup script runs before the session and cannot read the environment's variables, so a step that needs `DOPPLER_TOKEN` runs in the session.
- One failing step does not stop the others: run each step on its own, print what to fix and exit with an error at the end. Under `set -e`, the first refused host stops every later step.
- Download to a file with `curl -f` before passing it to another tool. Piped into `gpg`, a refused download shows as `gpg: no valid OpenPGP data found` instead of the refused host.

## Related documents

- [Working in a cloud session](../workflows/cloud-session.md)
- [Taskfiles](taskfiles.md)
- [Pipelines](pipeline.md)
- [Secrets](../infrastructure/secrets.md)
