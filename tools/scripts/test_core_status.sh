# Prints the numbers of the shards that failed, space separated, and nothing when all passed, inside the Odoo container.
# Needs SHARD_NUMBERS and TEST_RUN_DIR.
failed=""
for n in $SHARD_NUMBERS; do
  [[ "$(cat "$TEST_RUN_DIR/status/$n" 2>/dev/null)" = 0 ]] || failed="$failed $n"
done
echo $failed
