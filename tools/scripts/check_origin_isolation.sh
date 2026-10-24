#!/usr/bin/env bash
# Checks that permitted pods reach Odoo's health route through Traefik and directly, then checks that an untrusted pod
# with forged client headers reaches neither. Runs on a machine with kubectl and the cluster's kubeconfig.
# Usage: KUBECONFIG=infra/ansible/kubeconfig.yml tools/scripts/check_origin_isolation.sh
set -euo pipefail

IMAGE=docker.io/curlimages/curl:8.22.0@sha256:58adaa4e8dca9c988bae2aba4ab3434a0bb2da16bbe3f92dec39ec7785166777
TRAEFIK=http://traefik.kube-system.svc.cluster.local/web/health
ODOO=http://odoo.medilab.svc.cluster.local:8069/web/health
PROBES=()

cleanup() {
  local probe
  for probe in "${PROBES[@]}"; do
    kubectl -n "${probe%%/*}" delete job "${probe#*/}" --ignore-not-found --wait=false >/dev/null 2>&1 || true
  done
  return 0
}
trap cleanup EXIT

probe() {
  local namespace=$1 source=$2 target=$3 expected=$4 name output
  # A Job owns each probe pod, so application ReplicaSets cannot adopt a pod carrying their label.
  name=$(kubectl -n "$namespace" create -f - -o 'jsonpath={.metadata.name}' <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  generateName: origin-check-
spec:
  activeDeadlineSeconds: 90
  backoffLimit: 0
  ttlSecondsAfterFinished: 300
  template:
    metadata:
      labels:
        app.kubernetes.io/name: $source
    spec:
      automountServiceAccountToken: false
      restartPolicy: Never
      containers:
        - name: curl
          image: $IMAGE
          command: [sh, -c]
          args:
            - >-
              curl --silent --show-error --fail --max-time 5 --output /dev/null
              -H 'Host: lims.soltunemontepre.tech'
              -H 'Cf-Connecting-IP: 203.0.113.7'
              -H 'X-Forwarded-For: 203.0.113.7' '$target';
              printf '\\ncurl-exit=%s\\n' "\$?"
EOF
  ) || return 1
  PROBES+=("$namespace/$name")
  if ! kubectl -n "$namespace" wait --for=condition=complete "job/$name" --timeout=120s >/dev/null; then
    printf 'Could not finish the probe to %s.\n' "$target" >&2
    kubectl -n "$namespace" logs "job/$name" --pod-running-timeout=5s >&2 || true
    return 1
  fi
  output=$(kubectl -n "$namespace" logs "job/$name") || return 1
  if [[ "$output" == "curl-exit=$expected" || "$output" == *$'\n'"curl-exit=$expected" ]]; then
    if [[ "$expected" == 0 ]]; then
      printf 'Reachable from %s: %s\n' "$source" "$target"
    else
      printf 'Refused: %s\n' "$target"
    fi
    return 0
  fi
  printf 'Unexpected answer from %s for %s:\n%s\n' "$target" "$source" "$output" >&2
  return 1
}

kubectl -n medilab rollout status deployment/odoo --timeout=120s
kubectl -n kube-system rollout status deployment/traefik --timeout=120s

probe medilab cloudflared "$TRAEFIK" 0
probe kube-system traefik "$ODOO" 0

failed=0
for target in "$TRAEFIK" "$ODOO"; do
  if ! probe medilab origin-check "$target" 28; then
    failed=1
  fi
done
exit "$failed"
