#!/bin/bash
set -euo pipefail
umask 077
browser_user=()
if [[ $(id -u) == 0 ]]; then
  browser_user=(runuser -u pwuser --)
fi
install -d -m 0700 -o pwuser -g pwuser /tmp/medilab-fixture-tls
install -m 0600 -o pwuser -g pwuser /run/fixture-leaf/tls.key /tmp/medilab-fixture-tls/tls.key
install -m 0644 -o pwuser -g pwuser /run/fixture-leaf/tls.crt /tmp/medilab-fixture-tls/tls.crt
install -d -m 0700 -o pwuser -g pwuser /home/pwuser/.pki /home/pwuser/.pki/nssdb
if [[ ! -f /home/pwuser/.pki/nssdb/cert9.db ]]; then
  "${browser_user[@]}" certutil -N -d sql:/home/pwuser/.pki/nssdb --empty-password
fi
"${browser_user[@]}" certutil -A -d sql:/home/pwuser/.pki/nssdb -n medilab-fixture -t 'C,,' -i /run/fixture-ca/ca.crt
export NODE_EXTRA_CA_CERTS=/run/fixture-ca/ca.crt
export ONLYOFFICE_FIXTURE_TLS_DIR=/tmp/medilab-fixture-tls
exec "${browser_user[@]}" "$@"
