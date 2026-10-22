set -euo pipefail
. "$(dirname "$0")/cd_core_argocd.sh"

deadline=$((SECONDS + TIMEOUT))
last=""
while (( SECONDS < deadline )); do
  if state=$(argo app get odoo --refresh -o json 2> /dev/null); then
    revision=$(jq -r '.status.operationState.syncResult.revision // ""' <<< "$state")
    phase=$(jq -r '.status.operationState.phase // ""' <<< "$state")
    sync=$(jq -r '.status.sync.status // ""' <<< "$state")
    health=$(jq -r '.status.health.status // ""' <<< "$state")
    line="revision ${revision:0:7}, operation $phase, $sync, $health"
    [[ "$line" == "$last" ]] || echo "$line"
    last=$line

    git fetch -q origin main
    if [[ -n "$revision" ]] && git merge-base --is-ancestor "$RELEASE_COMMIT" "$revision" 2> /dev/null; then
      case "$phase" in
        Failed | Error)
          echo "The sync of the release failed: $(jq -r '.status.operationState.message' <<< "$state")" >&2
          exit 1
          ;;
      esac
      if [[ "$health" == Degraded ]]; then
        echo "The release is degraded: $(jq -r '.status.health.message // ""' <<< "$state")" >&2
        exit 1
      fi
      if [[ "$phase" == Succeeded && "$sync" == Synced && "$health" == Healthy ]]; then
        echo "The release is synced and healthy."
        exit 0
      fi
    fi
  else
    echo "Argo CD did not answer; trying again."
  fi
  sleep 15
done
echo "The release was not healthy within $TIMEOUT seconds." >&2
exit 1
