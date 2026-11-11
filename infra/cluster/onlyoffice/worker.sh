#!/bin/bash
set -euo pipefail
# Apply policy after the upstream service launcher sanitizes the parent environment.
[[ "$1" == /opt/medilab/onlyoffice/settings.json ]]
[[ -s "$1" ]]
node_config=$(cat "$1")
shift
binary=$1
shift
case "$binary" in
  /var/www/onlyoffice/documentserver/server/DocService/docservice|/var/www/onlyoffice/documentserver/server/FileConverter/converter) ;;
  *) exit 78 ;;
esac
export NODE_CONFIG="$node_config" PKG_EXECPATH="$binary"
exec "$binary" /opt/medilab/onlyoffice/worker-bootstrap.cjs "$@"
