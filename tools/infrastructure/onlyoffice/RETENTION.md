# Native cache retention fixture

`retention_probe.cjs` checks the pinned native garbage collector against the approved `604800`-second cache duration. It creates synthetic task records aged two and eight days and actual cache bytes, restores its process-local clock before invoking the native collector, and checks that the younger record and bytes survive while the older record and bytes are removed. It then removes its own remaining fixture.

Run it in a disposable container with no shared volumes or network:

```bash
timeout 45s podman --url unix:///run/user/1000/podman/podman.sock run --rm \
  --network none --name medilab-native-retention-probe \
  --env NODE_ENV=production-linux \
  --env NODE_CONFIG_DIR=/etc/onlyoffice/documentserver \
  --env MEDILAB_ONLYOFFICE_RETENTION_FIXTURE=isolated-empty \
  --entrypoint /bin/bash \
  --volume "$PWD/tools/infrastructure/onlyoffice:/opt/probe:ro" \
  --volume "$PWD/infra/cluster/onlyoffice/settings.json:/opt/settings.json:ro" \
  docker.io/onlyoffice/documentserver:9.4.0.1@sha256:3ab6ebc7c605e5a32b7ae3ff19daed4925090245acc8100ce2230bd766c88212 \
  -c 'export NODE_CONFIG="$(cat /opt/settings.json)"; export PKG_EXECPATH=/var/www/onlyoffice/documentserver/server/DocService/docservice; exec "$PKG_EXECPATH" /opt/probe/retention_probe.cjs'
```

The script refuses an unexpected binary, a different retention policy, or preexisting eligible or changed task records. Its native deadline is 30 seconds. The mounted settings contain public policy only. Credentials, signed URLs and tokens are not printed.

This is a native algorithm and filesystem fixture in a separate process. It does not establish seven elapsed days of retention, the supervised worker's cron execution, live task-state persistence or continuous recovery. Worker configuration, restart persistence and real Office saves need their separate runtime and integration evidence.
