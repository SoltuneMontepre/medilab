#!/bin/bash
set -euo pipefail
# The upstream service launcher sanitizes the parent environment before Supervisor starts.
test -s "$1"
node_config=$(cat "$1")
shift
export NODE_CONFIG="$node_config"
exec "$@"
