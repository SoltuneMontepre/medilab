# Runs the Medilab Sync frontend tests, and the Rust tests when cargo is installed. Sourced by task test:apps.
# Usage: . tools/scripts/test_apps.sh <app dir>
set -e
. tools/scripts/log.sh

cd "$1"
log_step "Medilab Sync frontend"
bun install --frozen-lockfile
bun test
if command -v cargo >/dev/null 2>&1; then
  log_step "Medilab Sync backend"
  cargo test --manifest-path src-tauri/Cargo.toml
else
  log_info "cargo not found, skipping the Rust tests. Install: winget install Rustlang.Rustup"
fi
log_ok "Application tests passed."
