#!/bin/bash
# Guard every application start, including container restarts within the same Pod.
set -euo pipefail
umask 077
workspace=${MEDILAB_WORKSPACE:-/opt/cloudbeaver/workspace}
mkdir -p "$workspace"
exec 9>>"$workspace/.medilab.lock"
flock -n 9 || { printf '%s\n' 'CloudBeaver workspace is in use.' >&2; exit 1; }
gson=(/opt/cloudbeaver/server/plugins/com.google.gson_*.jar)
state=$(java -cp "/bootstrap-bin:${gson[0]}" Workspace start)
if [[ "$state" == configured ]]; then
    unset CB_ADMIN_NAME CB_ADMIN_PASSWORD CB_SERVER_NAME CB_SERVER_URL
fi
unset CB_VERIFY_NAME CB_VERIFY_PASSWORD
rm -f /bootstrap-bin/readiness-cookie /bootstrap-bin/verification-failed
exec ./launch-product.sh
