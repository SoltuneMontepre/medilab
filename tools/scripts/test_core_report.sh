# Combines the coverage of the install and every shard into coverage.xml, inside the Odoo container.
# Prints the numbers of the shards that failed, space separated, and nothing when all passed.
# Needs SHARD_NUMBERS and TEST_RUN_DIR.
set -e
. "$(dirname "$0")/test_core_common.sh"

install_coverage
cd /mnt/extra-addons
python3 -m coverage combine -q --data-file="$TEST_RUN_DIR/coverage/.coverage" "$TEST_RUN_DIR/coverage"
python3 -m coverage xml -q --data-file="$TEST_RUN_DIR/coverage/.coverage" -o coverage.xml

failed=""
for n in $SHARD_NUMBERS; do
  [[ "$(cat "$TEST_RUN_DIR/status/$n" 2>/dev/null)" = 0 ]] || failed="$failed $n"
done
echo $failed
