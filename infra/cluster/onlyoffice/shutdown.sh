#!/bin/bash
set -euo pipefail
# The server waits at least 30s and can drain for 1830s with this pinned queue configuration.
body=$(curl --noproxy '*' --fail --silent --connect-timeout 2 --max-time 1860 \
  --request PUT http://127.0.0.1:8000/internal/cluster/inactive 2>/dev/null) || exit 1
test "$body" = true
