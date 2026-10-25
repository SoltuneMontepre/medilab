#!/bin/bash
set -euo pipefail
umask 077
# The upstream entrypoint interpolates the secret into JavaScript; use a safe random alphabet.
if [[ ! ${JWT_SECRET:-} =~ ^[A-Za-z0-9_-]{32,}$ ]]; then
  echo 'ONLYOFFICE configuration refused: JWT_SECRET requires at least 32 base64url characters.' >&2
  exit 1
fi
export NODE_CONFIG="$(cat /opt/medilab/onlyoffice/settings.json)"
export JWT_ENABLED=true JWT_HEADER=Medilab-Editor-Token JWT_IN_BODY=false
export ALLOW_PRIVATE_IP_ADDRESS=true ALLOW_META_IP_ADDRESS=false USE_UNAUTHORIZED_STORAGE=false
export DS_LOG_LEVEL=OFF NGINX_ACCESS_LOG=false PLUGINS_ENABLED=false
export NODE_EXTRA_CA_CERTS=/run/onlyoffice-ca/ca.crt
export SSL_CERTIFICATE_PATH=/run/onlyoffice-tls/tls.crt SSL_KEY_PATH=/run/onlyoffice-tls/tls.key
test -s "$NODE_EXTRA_CA_CERTS"
test -s "$SSL_CERTIFICATE_PATH"
test -s "$SSL_KEY_PATH"
sudo -u ds test -r "$NODE_EXTRA_CA_CERTS"
# Keep cached-file signatures valid across replacement for the lifetime of their existing URLs.
private_dir=/var/www/onlyoffice/Data/.private
test ! -L "$private_dir"
install -d -m 0700 "$private_dir"
secure_link_file="$private_dir/medilab-secure-link-secret"
test ! -L "$secure_link_file"
if [[ ! -e "$secure_link_file" ]]; then
  secret_tmp=$(mktemp "$private_dir/.secure-link.XXXXXX")
  pwgen -s 48 1 >"$secret_tmp"
  mv "$secret_tmp" "$secure_link_file"
fi
chmod 0600 "$secure_link_file"
export SECURE_LINK_SECRET="$(cat "$secure_link_file")"
[[ $SECURE_LINK_SECRET =~ ^[A-Za-z0-9]{48}$ ]]
# The upstream JSON editor preserves this mode; its final ownership pass gives it to ds.
chmod 0600 /etc/onlyoffice/documentserver/local.json
# Upstream ignores a false drain body and leaves curl unbounded.
install -m 0755 /opt/medilab/onlyoffice/shutdown.sh /usr/bin/documentserver-prepare4shutdown.sh
# Nginx errors can include the complete signed request URL. Patch templates as well as live includes.
find /etc/nginx /etc/onlyoffice/documentserver/nginx -type f \
  \( -name '*.conf' -o -name '*.tmpl' \) -exec sed -i -E \
  -e 's@^[[:space:]]*access_log[[:space:]].*;@access_log off;@' \
  -e 's@^[[:space:]]*error_log[[:space:]].*;@error_log /dev/null crit;@' {} +
# Do not export the upstream tail of raw log files to the container log collector.
exec /app/ds/run-document-server.sh >/dev/null 2>&1
