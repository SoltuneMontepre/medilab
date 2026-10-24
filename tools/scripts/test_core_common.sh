# Shared by the test_core_* scripts, which run inside the Odoo container.
# Needs MODULES and TEST_RUN_DIR.

install_coverage() {
  if python3 -c 'import coverage' >/dev/null 2>&1; then
    return 0
  fi
  pip install -q --root-user-action=ignore --break-system-packages --only-binary :all: coverage==7.10.7
  return $?
}

# Runs Odoo as the odoo user with the test database settings, then the given arguments.
odoo_without_coverage() {
  runuser -u odoo -- python3 -m odoo \
    --db_host "$HOST" --db_user "$USER" --db_password "$PASSWORD" --data-dir "$TEST_RUN_DIR/data" \
    --stop-after-init --log-level=test --test-enable "$@"
  return $?
}

# Runs Odoo like odoo_without_coverage, under coverage of the modules.
odoo_with_coverage() {
  runuser -u odoo -- python3 -m coverage run --parallel-mode --branch --source="$MODULES" --omit="*/tests/*" \
    --data-file="$TEST_RUN_DIR/coverage/.coverage" -m odoo \
    --db_host "$HOST" --db_user "$USER" --db_password "$PASSWORD" --data-dir "$TEST_RUN_DIR/data" \
    --stop-after-init --log-level=test --test-enable "$@"
  return $?
}

# Prepares fresh test databases for commerce tests before any demo accounting records exist.
prepare_vietnamese_accounting() {
  local scripts=/opt/medilab/scripts
  runuser -u odoo -- python3 -m odoo \
    --db_host "$HOST" --db_user "$USER" --db_password "$PASSWORD" --data-dir "$TEST_RUN_DIR/data" \
    --stop-after-init -d "$TEST_DB" -i base
  runuser -u odoo -- python3 -m odoo shell \
    --db_host "$HOST" --db_user "$USER" --db_password "$PASSWORD" --data-dir "$TEST_RUN_DIR/data" \
    --stop-after-init -d "$TEST_DB" < "$scripts/demo_bootstrap_set_country.py"
  runuser -u odoo -- python3 -m odoo \
    --db_host "$HOST" --db_user "$USER" --db_password "$PASSWORD" --data-dir "$TEST_RUN_DIR/data" \
    --stop-after-init -d "$TEST_DB" -i l10n_vn
  runuser -u odoo -- python3 -m odoo shell \
    --db_host "$HOST" --db_user "$USER" --db_password "$PASSWORD" --data-dir "$TEST_RUN_DIR/data" \
    --stop-after-init -d "$TEST_DB" < "$scripts/demo_bootstrap_accounting.py"
}
