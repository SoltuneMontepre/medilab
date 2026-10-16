# Checks the AI tooling prerequisites and syncs its environment. Sourced by task ai:setup.
# Usage: . tools/scripts/ai_setup.sh <AI tooling project dir>
set -e
. tools/scripts/log.sh

log_step "AI tooling"
if ! command -v uv >/dev/null 2>&1; then
  log_error "uv not found. Install: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi
if ! command -v npx >/dev/null 2>&1; then
  log_error "npx not found. Install Node.js: https://nodejs.org/en/download"
  exit 1
fi
if ! command -v git >/dev/null 2>&1; then
  log_error "git not found. Install: https://git-scm.com/downloads"
  exit 1
fi
uv sync --quiet --locked --project "$1"
