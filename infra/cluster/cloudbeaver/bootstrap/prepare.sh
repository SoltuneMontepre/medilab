#!/bin/bash
# Compile against the JSON library shipped in the exact CloudBeaver image.
set -euo pipefail
umask 077
workspace=${MEDILAB_WORKSPACE:-/opt/cloudbeaver/workspace}
mkdir -p "$workspace"
exec 9>>"$workspace/.medilab.lock"
flock -n 9 || { printf '%s\n' 'CloudBeaver workspace is in use.' >&2; exit 1; }
gson=(/opt/cloudbeaver/server/plugins/com.google.gson_*.jar)
javac -cp "${gson[0]}" -d /bootstrap-bin /bootstrap/*.java
java -cp "/bootstrap-bin:${gson[0]}" Workspace inspect
java -cp "/bootstrap-bin:${gson[0]}" Connections
