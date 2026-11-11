# Runs the Medilab Sync frontend tests, the Rust tests when cargo is installed, and the Medilab Mobile tests. Sourced by task test:apps.
# Usage: . tools/scripts/test_apps.sh <sync app dir> <mobile app dir>
set -e
. tools/scripts/log.sh

root=$PWD
cd "$1"
log_step "Medilab Sync frontend"
bun install --frozen-lockfile --ignore-scripts
bun test
if command -v cargo >/dev/null 2>&1; then
  log_step "Medilab Sync backend"
  cargo test --locked --manifest-path src-tauri/Cargo.toml
else
  log_info "cargo not found, skipping the Rust tests. Install: winget install Rustlang.Rustup"
fi
cd "$root/$2"
log_step "Medilab Mobile"
bun install --frozen-lockfile --ignore-scripts
bun run test
log_ok "Application tests passed."
