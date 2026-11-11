set -euo pipefail
. "$(dirname "$0")/cd_core_argocd.sh"

deadline=$((SECONDS + TIMEOUT))
last=""
revision=""
started=false
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
      started=true
      if [[ "$phase" == Failed || "$phase" == Error ]]; then
        echo "The sync of the release failed: $(jq -r '.status.operationState.message' <<< "$state")" >&2
        exit 1
      fi
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
if [[ "$started" == false ]]; then
  # The release never ran, as Argo CD was still syncing an older revision: rolling it back would blame it for that.
  echo "synced=false" >> "$GITHUB_OUTPUT"
  last_sync=${revision:0:7}
  echo "Argo CD did not start syncing the release within $TIMEOUT seconds; its last sync is of ${last_sync:-no revision}." \
    "Nothing is rolled back: look at the odoo application in Argo CD." >&2
  exit 1
fi
echo "The release was not healthy within $TIMEOUT seconds." >&2
exit 1
