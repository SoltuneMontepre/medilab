# Shared by the test_core_* scripts, which run inside the Odoo container.
# Needs MODULES and TEST_RUN_DIR.

install_coverage() {
  pip install -q --root-user-action=ignore --break-system-packages --only-binary :all: coverage
  return $?
}

# Runs Odoo as the odoo user under coverage with the test database settings, then the given arguments.
odoo_with_coverage() {
  runuser -u odoo -- python3 -m coverage run --parallel-mode --branch --source="$MODULES" --omit="*/tests/*" \
    --data-file="$TEST_RUN_DIR/coverage/.coverage" -m odoo \
    --db_host "$HOST" --db_user "$USER" --db_password "$PASSWORD" --data-dir "$TEST_RUN_DIR/data" \
    --stop-after-init --log-level=test --test-enable "$@"
  return $?
}
