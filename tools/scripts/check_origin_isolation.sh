#!/usr/bin/env bash
# Checks that only Cloudflare reaches the origin: a throwaway pod that is not cloudflared sends a sign-in with a forged
# Cf-Connecting-IP to Traefik and to Odoo, and the network policies must drop both. Runs on a machine with kubectl and
# the cluster's kubeconfig; see Provisioning.
# Usage: KUBECONFIG=infra/ansible/kubeconfig.yml tools/scripts/check_origin_isolation.sh
set -euo pipefail

IMAGE=docker.io/curlimages/curl:8.22.0@sha256:58adaa4e8dca9c988bae2aba4ab3434a0bb2da16bbe3f92dec39ec7785166777
TARGETS=(
  http://traefik.kube-system.svc.cluster.local/medilab/api/v1/sign-in
  http://odoo.medilab.svc.cluster.local:8069/medilab/api/v1/sign-in
)

failed=0
for target in "${TARGETS[@]}"; do
  # curl exits 28 when its connection times out and 7 when it is refused, as when a network policy drops it.
  output=$(kubectl -n medilab run "origin-check-$RANDOM" --rm -i --quiet --restart=Never --image="$IMAGE" \
    --command -- sh -c "curl --silent --max-time 5 --output /dev/null -X POST \
      -H 'Cf-Connecting-IP: 203.0.113.7' '$target'; echo curl-exit=\$?" 2>&1 || true)
  case "$output" in
    *curl-exit=28* | *curl-exit=7*) printf 'Refused: %s\n' "$target" ;;
    *curl-exit=*)
      printf 'REACHED: %s answered a pod that is not cloudflared.\n' "$target"
      failed=1
      ;;
    *)
      printf 'Could not check %s:\n%s\n' "$target" "$output"
      failed=1
      ;;
  esac
done
exit "$failed"
