# Installs or verifies OfficeCLI from the repository root. Sourced by task docs:setup.
# Usage: . tools/scripts/docs_setup.sh <OfficeCLI version>
set -e
. tools/scripts/log.sh

expected_officecli_version="$1"
if ! command -v officecli >/dev/null 2>&1; then
  if ! command -v npm >/dev/null 2>&1; then
    log_error "npm not found. Install Node.js: https://nodejs.org/en/download"
    exit 1
  fi
  log_info "Installing OfficeCLI $expected_officecli_version with npm."
  # Without install scripts, the first officecli run downloads the pinned binary and checks its SHA256.
  npm install -g --ignore-scripts --silent "@officecli/officecli@$expected_officecli_version"
fi

installed_officecli_version=$(officecli --version)
installed_officecli_version=${installed_officecli_version%$'\r'}
if [[ "$installed_officecli_version" != "$expected_officecli_version" ]]; then
  log_error "OfficeCLI $installed_officecli_version found; expected $expected_officecli_version. Install @officecli/officecli@$expected_officecli_version with npm and ensure it is first on PATH."
  exit 1
fi
log_ok "OfficeCLI $installed_officecli_version ready."
