#!/bin/bash
set -euo pipefail
umask 077
install -d -m 0700 -o odoo -g odoo /tmp/medilab-fixture-tls
install -m 0600 -o odoo -g odoo /run/fixture-leaf/tls.key /tmp/medilab-fixture-tls/tls.key
install -m 0644 -o odoo -g odoo /run/fixture-leaf/tls.crt /tmp/medilab-fixture-tls/tls.crt
export ONLYOFFICE_FIXTURE_TLS_DIR=/tmp/medilab-fixture-tls
exec setpriv --reuid=odoo --regid=odoo --init-groups --no-new-privs /entrypoint.sh "$@"
