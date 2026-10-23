# Installs the modules in the test database and runs their at-install tests, inside the Odoo container.
# Needs MODULES, TAGS, TEST_DB and TEST_RUN_DIR. INSTALL_COVERAGE=false installs without coverage.
set -e
. "$(dirname "$0")/test_core_common.sh"

runuser -u odoo -- mkdir -p "$TEST_RUN_DIR/coverage" "$TEST_RUN_DIR/status"
cd /mnt/extra-addons
if [[ "$INSTALL_COVERAGE" = false ]]; then
  odoo_without_coverage -d "$TEST_DB" -i "$MODULES" --test-tags "$TAGS,-post_install" --log-handler=odoo.tests.result:ERROR
else
  install_coverage
  odoo_with_coverage -d "$TEST_DB" -i "$MODULES" --test-tags "$TAGS,-post_install" --log-handler=odoo.tests.result:ERROR
fi
