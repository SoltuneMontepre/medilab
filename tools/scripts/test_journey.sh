# Run the connected journey with Playwright from src/tests in Task's shell.
# Usage: . test_journey.sh /path/to/log.sh run|watch [flow]
# Task supplies MEDILAB_URL. A flow such as wf-01 runs only the spec of that flow, on what the last journey left. The
# watch mode opens each actor's browser on the screen and slows every action down; MEDILAB_JOURNEY_WATCH_DELAY sets the
# wait in milliseconds.
set -e
. "$1"

journey_mode="$2"
journey_flow="${3:-}"
log_step "Connected journey"
log_link "Odoo" "$MEDILAB_URL"

if ! command -v bun >/dev/null 2>&1 || ! command -v bunx >/dev/null 2>&1; then
  log_error "Bun is not installed. Install it from https://bun.sh/docs/installation, then reopen your terminal."
  exit 1
fi

if ! bun --eval 'try { const response = await fetch(process.env.MEDILAB_URL.replace(/\/$/, "") + "/web/health", { signal: AbortSignal.timeout(5000) }); if (!response.ok) process.exit(1); } catch { process.exit(1); }'; then
  log_error "Odoo is not reachable at $MEDILAB_URL. Start this checkout with task up, then retry."
  log_info "To choose another port, pass MEDILAB_URL=http://localhost:<port>."
  exit 1
fi

log_info "Installing the test dependencies and checking the Chromium of Playwright."
bun install --frozen-lockfile --ignore-scripts
bunx playwright install chromium

if [[ "$journey_mode" == watch ]]; then
  export MEDILAB_JOURNEY_WATCH=1
  log_info "Each actor's browser opens on the screen; the current step shows at the bottom of the page."
fi
set --
if [[ -n "$journey_flow" ]]; then
  log_info "Running only the flow $journey_flow, on what the last journey handed over."
  set -- "$@" "$journey_flow"
fi
journey_status=0
bunx playwright test "$@" || journey_status=$?
log_info "Steps, screens and each actor's video: bunx playwright show-report playwright/.output/report (from src/tests)."
if [[ "$journey_status" != 0 ]]; then
  log_error "A flow failed or stopped. A flow whose starting records are missing is skipped with their names."
  exit "$journey_status"
fi
log_ok "Every flow continued from the one before it."
