#!/usr/bin/env bash
set -uo pipefail

RED=$'\033[31m'
YELLOW=$'\033[33m'
GREEN=$'\033[32m'
RESET=$'\033[0m'

ADDONS_PATH="${ADDONS_PATH:-/mnt/extra-addons}"
ODOO_VERSION="${ODOO_VERSION:-20.0}"

EXCLUDED_MODULES_FILE="${EXCLUDED_MODULES_FILE:-/tmp/excluded-modules.txt}"
declare -A EXCLUDED_MODULES=()
if [[ -f "$EXCLUDED_MODULES_FILE" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="${line// /}"
    [[ -n "$line" ]] && EXCLUDED_MODULES["$line"]=1
  done <"$EXCLUDED_MODULES_FILE"
fi

MODULES=()
for d in "$ADDONS_PATH"/*/; do
  [[ -f "${d}__manifest__.py" ]] || continue
  name="$(basename "${d%/}")"
  [[ -n "${EXCLUDED_MODULES[$name]+x}" ]] && continue
  MODULES+=("${d%/}")
done

if [[ "${#MODULES[@]}" -eq 0 ]]; then
  echo "${RED}[ERROR] No Odoo modules found in $ADDONS_PATH${RESET}" >&2
  exit 1
fi

if [[ "${#EXCLUDED_MODULES[@]}" -gt 0 ]]; then
  echo "[INFO] Skipping ${#EXCLUDED_MODULES[@]} excluded module(s)"
fi
echo "[INFO] Linting ${#MODULES[@]} modules against Odoo $ODOO_VERSION"
echo
status=0

if command -v git >/dev/null 2>&1; then
  _GIT=$(mktemp -d)
  trap 'rm -rf "$_GIT"' EXIT
  git init --quiet "$_GIT"
  export GIT_DIR="$_GIT/.git" GIT_WORK_TREE="$ADDONS_PATH"
fi

count_issues() {
  local log_file="$1"
  grep -cE '^\S+\.py:[0-9]+:[0-9]+: [A-Z][0-9]+:' "$log_file" || true
  return 0
}
print_colored() {
  local log_file="$1"
  local color="$2"
  sed -E "s/^(\S+\.py:[0-9]+:[0-9]+: [A-Z][0-9]+:.*)\$/${color}\1${RESET}/" "$log_file"
  return 0
}

echo "==> pylint-odoo${ODOO_LINT_ADVISORY:+ (advisory)}"
echo
ODOO_LOG=$(mktemp)
ODOO_ARGS=(--load-plugins=pylint_odoo -d all -e odoolint
  -d missing-readme -d manifest-required-author -d manifest-deprecated-key
  -d manifest-superfluous-key -d license-allowed -d manifest-required-key-app
  -d missing-odoo-file-app -d category-allowed-app -d manifest-version-format)
if [[ -n "${PYLINT_RCFILE:-}" ]]; then
  ODOO_ARGS=(--rcfile="$PYLINT_RCFILE")
fi
odoo_status=0
python3 -m pylint "${ODOO_ARGS[@]}" \
  --enable=E0013,E0015,W0012 \
  --output-format=text --msg-template='{path}:{line}:{column}: {msg_id}: {msg} ({symbol})' \
  --valid-odoo-versions="$ODOO_VERSION" \
  "${MODULES[@]}" >"$ODOO_LOG" 2>&1 || odoo_status=$?
odoo_count=$(count_issues "$ODOO_LOG")
odoo_config_count=$(grep -Ec ' (E0013|E0015|W0012):' "$ODOO_LOG" || true)
print_colored "$ODOO_LOG" "$([[ -n "${ODOO_LINT_ADVISORY:-}" ]] && echo "$YELLOW" || echo "$RED")"

echo
if [[ "$odoo_config_count" -gt 0 ]] || ((odoo_status & 33)) || [[ "$odoo_status" -ne 0 && "$odoo_count" -eq 0 ]]; then
  echo "${RED}[ERROR] pylint-odoo could not complete (exit $odoo_status)${RESET}" >&2
  status=1
elif [[ "$odoo_count" -gt 0 ]]; then
  if [[ -n "${ODOO_LINT_ADVISORY:-}" ]]; then
    echo "${YELLOW}[WARN] pylint-odoo: $odoo_count issue(s)${RESET}"
  else
    echo "${RED}[ERROR] pylint-odoo: $odoo_count issue(s)${RESET}" >&2
    status=1
  fi
else
  echo "${GREEN}[OK] pylint-odoo: no issues${RESET}"
fi

unset GIT_DIR GIT_WORK_TREE || true

echo
echo "==> pylint (errors only)"
echo
CORE_LOG=$(mktemp)
core_status=0
python3 -m pylint \
  --rcfile=/dev/null \
  --output-format=text --msg-template='{path}:{line}:{column}: {msg_id}: {msg} ({symbol})' \
  --errors-only \
  --disable=no-member,import-error,no-name-in-module,not-callable,assigning-non-slot,access-member-before-definition \
  "${MODULES[@]}" >"$CORE_LOG" 2>&1 || core_status=$?
core_count=$(count_issues "$CORE_LOG")
print_colored "$CORE_LOG" "$RED"

echo
if [[ "$core_status" -ne 0 && "$core_count" -eq 0 ]]; then
  echo "${RED}[ERROR] pylint could not complete (exit $core_status)${RESET}" >&2
  status=1
elif [[ "$core_count" -gt 0 ]]; then
  echo "${RED}[ERROR] pylint: $core_count error(s)${RESET}" >&2
  status=1
else
  echo "${GREEN}[OK] pylint: no errors${RESET}"
fi

echo
echo "==> Summary"
echo "    pylint-odoo : $odoo_count issue(s)$([[ -n "${ODOO_LINT_ADVISORY:-}" ]] && echo " (advisory)")"
echo "    pylint      : $core_count issue(s)"
echo

if [[ "$status" -ne 0 ]]; then
  echo "${RED}[FAILED] Lint failed${RESET}" >&2
  exit "$status"
fi

echo "${GREEN}[COMPLETED] Lint passed${RESET}"
