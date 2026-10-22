# Runs a command, prints its output as it arrives, and returns 1 when that output contains a warning.
# A failing command keeps its own status when it logged no warning.
# Sourced from the repository root. Task's shell runs it on Linux and Windows.
# Usage: . tools/scripts/run_strict.sh <command> [args...]

run_strict_plain() {
  rest="$1"
  built=""
  while [[ "$rest" == *$'\033'* ]]; do
    built="${built}${rest%%$'\033'*}"
    rest="${rest#*$'\033'}"
    if [[ "$rest" == '['* ]]; then
      rest="${rest#*m}"
    fi
  done
  printf '%s' "${built}${rest}"
  return 0
}

run_strict_check() {
  found=0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    printf '%s\n' "$line"
    plain="$(run_strict_plain "$line")"
    if [[ "$plain" == *" WARNING "* || "$plain" == *"level=warning"* || "$plain" == *"UserWarning"* || "$plain" == *"DeprecationWarning"* ]]; then
      found=1
    fi
  done
  if [[ "$found" -eq 1 ]]; then
    . tools/scripts/log.sh
    log_error "A warning was logged. Fix it, then run this again."
    return 1
  fi
  return 0
}

run_strict() {
  if [[ "$#" -eq 0 ]]; then
    printf 'usage: . tools/scripts/run_strict.sh <command> [args...]\n' >&2
    return 2
  fi
  set +e
  set -o pipefail
  "$@" 2>&1 | run_strict_check
  status="$?"
  return "$status"
}

set +e
run_strict "$@"
status="$?"
return "$status"
