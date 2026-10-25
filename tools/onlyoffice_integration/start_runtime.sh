#!/bin/bash
set -euo pipefail
# This HTTP-only fixture uses the production worker bootstrap; full TLS startup is checked separately.
unset NODE_CONFIG
install -d -m 0700 -o ds -g ds /run/onlyoffice-runtime
for service in docservice converter; do
  if [[ $service == docservice ]]; then
    binary=/var/www/onlyoffice/documentserver/server/DocService/docservice
  else
    binary=/var/www/onlyoffice/documentserver/server/FileConverter/converter
  fi
  supervisor_file="/etc/supervisor/conf.d/ds-$service.conf"
  worker_command="command=/bin/bash /opt/medilab/onlyoffice/worker.sh /opt/medilab/onlyoffice/settings.json $binary"
  sed -i "s|^command=$binary$|$worker_command|" "$supervisor_file"
  grep -Fxq "$worker_command" "$supervisor_file"
done
find /etc/nginx /etc/onlyoffice/documentserver/nginx -type f \
  \( -name '*.conf' -o -name '*.tmpl' \) -exec sed -i -E \
  -e 's@^[[:space:]]*access_log[[:space:]].*;@access_log off;@' \
  -e 's@^[[:space:]]*error_log[[:space:]].*;@error_log /dev/null crit;@' {} +
exec /app/ds/run-document-server.sh >/dev/null 2>&1
