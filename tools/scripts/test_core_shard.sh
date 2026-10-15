# Runs the test classes of one shard in its own copy of the test database, inside the Odoo container.
# Writes the exit status to $TEST_RUN_DIR/status/<shard> and always exits 0, so one failed shard does not stop the others.
# Needs MODULES, SHARD, TEST_DB and TEST_RUN_DIR.
. "$(dirname "$0")/test_core_common.sh"

status_file="$TEST_RUN_DIR/status/$SHARD"
shard_db="${TEST_DB}_$SHARD"
filestore="$TEST_RUN_DIR/data/filestore"
tags=$(cat "$TEST_RUN_DIR/shards/$SHARD.txt")
if [[ -z "$tags" ]]; then
  echo 0 > "$status_file"
  exit 0
fi

install_coverage
if [[ -d "$filestore/$TEST_DB" ]]; then
  runuser -u odoo -- cp -a "$filestore/$TEST_DB" "$filestore/$shard_db"
fi
cd /mnt/extra-addons
odoo_with_coverage -d "$shard_db" --test-tags "$tags" 2>&1 | sed -u "s/^/[shard $SHARD] /"
echo "${PIPESTATUS[0]}" > "$status_file"
