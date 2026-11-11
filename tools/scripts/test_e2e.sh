# Prepare and launch Cypress from src/tests in Task's shell.
# Usage: . test_e2e.sh run|open|tap|help /path/to/log.sh.
# Task supplies MEDILAB_E2E_URL and, in Tap mode, MEDILAB_TAP_BROWSER.
set -e
. "$2"

e2e_mode="$1"
export MEDILAB_URL="$MEDILAB_E2E_URL"
log_step "Browser tests"
log_link "Odoo" "$MEDILAB_URL"

if [[ "$e2e_mode" == help ]]; then
  printf '\n'
  printf '%s\n' \
    'Run these commands from the repository root, in PowerShell or your usual terminal.' \
    '' \
    '1. Install Bun from https://bun.sh/docs/installation and Node.js 22.x, 24.x or >=26.' \
    '   Start Docker or Podman.' \
    '2. Start this checkout with its existing demo data: task up' \
    '   A new local demo is set up with task setup:fresh:select, then task setup:fresh.' \
    '   See README.md for the full setup commands.' \
    '3. Open Cypress App: task test:e2e:open' \
    '   Choose E2E Testing, a browser, Start E2E Testing, then a .cy.js file.' \
    '4. Run every browser test in the terminal: task test:e2e' \
    '   Run only some: task test:e2e GREP=TC-WF01-A5, or SPEC=cypress/e2e/login.cy.js' \
    '5. Open an AI-driven Chrome session: task test:e2e:tap:open' \
    '   Select another Chromium browser with TAP_BROWSER=edge, chromium or electron.' \
    '   Inspect it from another terminal: task test:e2e:tap TAP_ARGS="status --json"' \
    '   AI workflow and installed skills: docs/workflows/cypress-tap.md' \
    '' \
    'The launch commands install the locked dependencies and the matching Cypress binary.' \
    'They check the displayed Odoo URL before launching Cypress.' \
    '' \
    'Different Odoo port? Pass its URL to either command:' \
    '  task test:e2e:open MEDILAB_URL=http://localhost:8169' \
    '  task test:e2e MEDILAB_URL=http://localhost:8169' \
    'For repeated use, save MEDILAB_URL in tools/infrastructure/.env.' \
    '' \
    'Preparing a disposable E2E app? task test:e2e:app installs modules/demo data,' \
    'configures the buckets, starts Odoo, and waits for its health endpoint.' \
    'For changes to installed Odoo modules, use task upgrade.' \
    'After upgrading Cypress, close the old app window and run task test:e2e:open.' \
    '' \
    'If Odoo is unreachable, run task up, open the displayed URL, and inspect task logs.' \
    'Tests use demo.<role>; set MEDILAB_DEMO_PASSWORD if the demo password was changed.' \
    'Tests change demo records. Use a local demo database.' \
    '' \
    'Full guide: docs/conventions/testing.md#running-browser-tests'
  return 0
fi

if [[ "$e2e_mode" != run && "$e2e_mode" != open && "$e2e_mode" != tap ]]; then
  log_error "Unknown browser-test mode. Use task test:e2e, task test:e2e:open or task test:e2e:tap:open."
  exit 2
fi

if [[ "$e2e_mode" == tap ]]; then
  case "$MEDILAB_TAP_BROWSER" in
    chrome|chromium|edge|electron) ;;
    *) log_error "Tap needs Chrome, Chromium, Edge or Electron. Set TAP_BROWSER to one of these browsers."; exit 2 ;;
  esac
fi

if ! command -v bun >/dev/null 2>&1 || ! command -v bunx >/dev/null 2>&1; then
  log_error "Bun is not installed. Install it from https://bun.sh/docs/installation, then reopen your terminal."
  exit 1
fi

unset ELECTRON_RUN_AS_NODE
log_info "Checking Odoo. Setup instructions: task test:e2e:help."
if ! bun --eval 'try { const response = await fetch(process.env.MEDILAB_URL.replace(/\/$/, "") + "/web/health", { signal: AbortSignal.timeout(5000) }); if (!response.ok) process.exit(1); } catch { process.exit(1); }'; then
  log_error "Odoo is not reachable at $MEDILAB_URL. Start this checkout with task up, then retry."
  log_info "Read task logs if startup fails. To choose another port, pass MEDILAB_URL=http://localhost:<port>."
  log_info "For demo setup and port selection, run task test:e2e:help."
  exit 1
fi

log_info "Installing the test dependencies and checking the Cypress binary."
bun install --frozen-lockfile --ignore-scripts
bunx cypress install

if [[ "$e2e_mode" == tap ]]; then
  log_info "Use task test:e2e:tap TAP_ARGS='sessions --json' from another terminal."
  bunx cypress open --e2e --browser "$MEDILAB_TAP_BROWSER"
elif [[ "$e2e_mode" == open ]]; then
  log_info "Choose E2E Testing, a browser, Start E2E Testing, then the test file."
  bunx cypress open
else
  set --
  if [[ -n "${MEDILAB_E2E_SPEC:-}" ]]; then
    log_info "Running only the specs matching $MEDILAB_E2E_SPEC."
    set -- "$@" --spec "$MEDILAB_E2E_SPEC"
  fi
  if [[ -n "${MEDILAB_E2E_GREP:-}" ]]; then
    log_info "Running only the tests whose title contains $MEDILAB_E2E_GREP."
    set -- "$@" --expose "grep=$MEDILAB_E2E_GREP"
  fi
  bun run test "$@"
  log_ok "Browser tests passed."
fi
