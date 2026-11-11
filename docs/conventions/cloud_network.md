# Cloud network

How scripts, Dockerfiles and the setup script are written for a Claude Code cloud session, where every outbound connection goes through the session's proxy. Setting up and using a session is in [Working in a cloud session](../workflows/cloud-session.md).

## Connections

- Add every host a script needs to the Allowed domains of [the environment](../workflows/cloud-session.md#set-up-the-environment).
- Use HTTPS URLs, including `apt` sources: `sed -i 's|http://|https://|g' /etc/apt/sources.list.d/*.sources`.
- Install tools from package registries: `uv tool install`, `npm` and signed `apt` repositories.
- Trust the proxy's certificate bundle, `/root/.ccr/ca-bundle.crt`. It holds the public roots too, so a tool can use it in place of the system bundle.
- Check which hosts the proxy refused with `curl -sS "$HTTPS_PROXY/__agentproxy/status"`.

## Hosts

| Host                                   | Used for                                |
| -------------------------------------- | --------------------------------------- |
| `packages.doppler.com`                 | Doppler CLI `apt` key and packages      |
| `api.doppler.com`                      | Secrets read through `DOPPLER_TOKEN`    |
| `pkg-containers.githubusercontent.com` | Layers of `ghcr.io` images              |
| `mirror.gcr.io`                        | Docker Hub images, as the Docker mirror |

## Docker builds

Build with the host network, the proxy as a build argument and its certificate as a build secret:

```bash
docker build --network host \
  --build-arg HTTPS_PROXY="$HTTPS_PROXY" \
  --secret id=proxy_ca,src=/root/.ccr/ca-bundle.crt \
  -f <Dockerfile> <context>
```

```dockerfile
ARG HTTPS_PROXY

RUN --mount=type=secret,id=proxy_ca,mode=0444 \
    apt-get -o Acquire::https::CaInfo=/run/secrets/proxy_ca update \
    && SSL_CERT_FILE=/run/secrets/proxy_ca uv pip install ...
```

- Mount the secret with `mode=0444`, so `apt`'s `_apt` user reads it.
- Keep the certificate in the secret, never in a `COPY`, so it stays out of the image.

## Setup script

- Run each step on its own: a failing step prints what to fix, the others still run, and the script exits with an error at the end.
- Download with `curl -f` to a file, then pass the file to the next tool.
- Run steps that need the environment's variables, such as `DOPPLER_TOKEN`, in the session.

## Related documents

- [Working in a cloud session](../workflows/cloud-session.md)
- [Taskfiles](taskfiles.md)
- [Secrets](../infrastructure/secrets.md)
