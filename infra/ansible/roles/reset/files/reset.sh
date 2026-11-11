#!/usr/bin/env bash
# Backs up the database, recreates it empty, has Argo CD sync the odoo application so its upgrade Job installs every module
# on it, restarts Odoo and checks the company is on VND with the demo data.
# Runs on a k3s server as root through the reset role. Usage: reset.sh <namespace> <cluster> <database> <application>

set -euo pipefail

namespace="$1"
cluster="$2"
database="$3"
application="$4"
backup="${cluster}-reset"

kubectl() {
  /usr/local/bin/k3s kubectl "$@"
}

section() {
  local title="$1"
  printf '\n== %s\n' "$title"
  return 0
}

psql_primary() {
  local target="$1"
  shift
  local primary
  primary=$(kubectl get pod -n "$namespace" -l "cnpg.io/cluster=${cluster},cnpg.io/instanceRole=primary" -o name)
  kubectl exec -n "$namespace" "$primary" -c postgres -- psql -v ON_ERROR_STOP=1 -d "$target" "$@"
}

section "Backup"
kubectl delete backup.postgresql.cnpg.io "$backup" -n "$namespace" --ignore-not-found --wait=true
kubectl apply -n "$namespace" -f - <<EOF
apiVersion: postgresql.cnpg.io/v1
kind: Backup
metadata:
  name: ${backup}
spec:
  cluster:
    name: ${cluster}
  method: plugin
  pluginConfiguration:
    name: barman-cloud.cloudnative-pg.io
EOF
kubectl wait backup.postgresql.cnpg.io "$backup" -n "$namespace" --for=jsonpath='{.status.phase}'=completed --timeout=1800s

section "Database"
psql_primary postgres \
  -c "DROP DATABASE IF EXISTS ${database} WITH (FORCE)" \
  -c "CREATE DATABASE ${database} OWNER ${database}"

section "Sync"
started=$(date -u +%Y-%m-%dT%H:%M:%SZ)
kubectl patch application "$application" -n argocd --type=merge \
  -p '{"operation":{"initiatedBy":{"username":"cd-reset"},"sync":{"revision":"main"}}}'
phase=""
for _ in $(seq 240); do
  state=$(kubectl get application "$application" -n argocd \
    -o jsonpath='{.status.operationState.startedAt} {.status.operationState.phase}')
  read -r operation_started phase <<<"$state"
  if [[ ! "$operation_started" < "$started" ]] && [[ "$phase" =~ ^(Succeeded|Failed|Error)$ ]]; then
    break
  fi
  phase=""
  sleep 15
done
kubectl get application "$application" -n argocd -o jsonpath='{.status.operationState.message}{"\n"}'
test "$phase" = "Succeeded"

section "Odoo"
kubectl rollout restart deployment/odoo -n "$namespace"
kubectl rollout status deployment/odoo -n "$namespace" --timeout=600s

section "Check"
currency=$(psql_primary "$database" -Atc \
  "select r.name from res_company c join res_currency r on r.id = c.currency_id order by c.id limit 1")
demo=$(psql_primary "$database" -Atc "select state from ir_module_module where name = 'sol_demo'")
printf 'Currency: %s\nsol_demo: %s\n' "$currency" "$demo"
test "$currency" = "VND"
test "$demo" = "installed"
