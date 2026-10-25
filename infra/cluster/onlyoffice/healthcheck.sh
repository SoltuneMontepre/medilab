#!/bin/bash
set -euo pipefail
# A stopped converter and HTTP 200/false must both refuse new editing sessions.
timeout 2s supervisorctl status ds:docservice ds:converter >/dev/null 2>&1
timeout 2s sudo -u ds python3 /opt/medilab/onlyoffice/inspect_config.py >/dev/null 2>&1
probe_host=${ONLYOFFICE_PROBE_HOST:-onlyoffice.medilab.svc.cluster.local}
body=$(curl --noproxy '*' --fail --silent --connect-timeout 2 --max-time 4 \
  --cacert /run/onlyoffice-ca/ca.crt --resolve "${probe_host}:443:127.0.0.1" \
  "https://${probe_host}/healthcheck" 2>/dev/null) || exit 1
test "$body" = true
