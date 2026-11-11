#!/bin/bash
set -euo pipefail
umask 077
gson=(/opt/cloudbeaver/server/plugins/com.google.gson_*.jar)
exec java -Xmx32m -cp "/bootstrap-bin:${gson[0]}" Readiness
