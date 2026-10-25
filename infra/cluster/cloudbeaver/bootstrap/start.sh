#!/bin/bash
# Guard every application start, including container restarts within the same Pod.
set -euo pipefail
umask 077
gson=(/opt/cloudbeaver/server/plugins/com.google.gson_*.jar)
state=$(java -cp "/bootstrap-bin:${gson[0]}" Workspace start)
if [[ "$state" == initialized ]]; then
    unset CB_ADMIN_NAME CB_ADMIN_PASSWORD CB_SERVER_NAME CB_SERVER_URL
fi
exec ./launch-product.sh
