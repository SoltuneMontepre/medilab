# Installs or upgrades modules in a one-shot Odoo container, and fails when that run logs a warning.
# Sourced from the repository root. Task's shell runs it on Linux and Windows.
# Usage: . tools/scripts/odoo_upgrade.sh <modules>
# modules is all, or a comma-separated list.

odoo_upgrade() {
  modules="${1:-all}"
  set +e
  if [[ "$modules" == "all" ]]; then
    . tools/scripts/run_strict.sh docker compose run --rm -T -e PYTHONUNBUFFERED=1 odoo --stop-after-init -u all
    status="$?"
    return "$status"
  fi
  . tools/scripts/run_strict.sh docker compose run --rm -T -e PYTHONUNBUFFERED=1 odoo --stop-after-init -i "$modules" -u "$modules"
  status="$?"
  return "$status"
}

odoo_upgrade "$@"
status="$?"
return "$status"
