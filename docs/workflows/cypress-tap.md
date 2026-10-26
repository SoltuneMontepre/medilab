# Cypress Tap and AI Skills

Use the project's Cypress skills to author, review and debug browser specs. The four official skills and their references live in `.agents/skills/`, where Cursor, Antigravity and Codex discover them directly; `.claude/skills/` exposes them to Claude Code through short entry points that link to `.agents/skills/`. Restart the agent session after first checkout so it discovers the skills.

## Prepare a live session

Prepare the demo and URL as described in [Running browser tests](../conventions/testing.md#running-browser-tests). From this worktree's root, start its E2E session with Chrome:

```powershell
task test:e2e:tap:open
# A demo on another port:
task test:e2e:tap:open MEDILAB_URL=http://localhost:8169
```

Set `TAP_BROWSER=edge`, `chromium` or `electron` to choose another installed supported browser. Chrome is the default; Cypress 16 deprecates Electron as a test browser.

Keep that command running. In another terminal at the same worktree root:

```powershell
task test:e2e:tap TAP_ARGS='sessions --json'
task test:e2e:tap TAP_ARGS='status --json'
task test:e2e:tap TAP_ARGS='specs --json'
```

`TAP_ARGS` preserves CLI flags through the npm Task wrapper in PowerShell and passes them as data rather than shell code. The wrapper uses the locked Cypress package in `src/tests`, clears `ELECTRON_RUN_AS_NODE`, filters sessions to this worktree's E2E project and binds the selected PID. It refuses another project's session and asks for `--session <pid>` if more than one matches. Carry that observed PID on every subsequent command in a debugging loop. Tap works with Electron, Chrome, Chromium and Edge; headless CI continues to use `task test:e2e`. [Official Tap guide](https://docs.cypress.io/app/tooling/cypress-tap)

## Choose the skill

| Task | Skill |
| --- | --- |
| Create or fix a Cypress spec | `cypress-author` |
| Review or explain an existing spec | `cypress-explain` |
| Verify a Cypress API or configuration | `cypress-docs` |
| Run a spec and inspect the live browser | `cypress-tap` |

Read the [testing conventions](../conventions/testing.md#shared-browser-commands), current config, shared commands and the relevant specs first. Reuse the demo-role and record helpers. For live work, follow the [official Tap skill](../../.agents/skills/cypress-tap/SKILL.md) and only load the references needed for the task.

## Run and inspect

Capture `status --json` before dispatching one path returned by `specs`:

```powershell
task test:e2e:tap TAP_ARGS='run cypress/e2e/login.cy.js --json'
task test:e2e:tap TAP_ARGS='status --json'
task test:e2e:tap TAP_ARGS='reporter --json'
```

A successful `run` command confirms dispatch. Poll one status request at a time, with a bounded wait, until the requested spec has a nonempty changed `startedAt` and a terminal verdict. Require actual test counts before reporting a pass. Treat command errors as failures; retry transient partial status payloads. Build failures and watcher reruns follow the [upstream lifecycle contract](../../.agents/skills/cypress-tap/references/session-lifecycle.md).

Read failures before editing or rerunning, using the test and command IDs returned by `reporter`. Bound app reads and clear a historical pin afterwards:

```powershell
task test:e2e:tap TAP_ARGS='dom --selector body --max-chars 6000'
task test:e2e:tap TAP_ARGS='aria --max-nodes 80'
task test:e2e:tap TAP_ARGS='pin --clear'
```

Use command-specific `--help` for the installed beta CLI. Saving a watched file reruns the selected spec, which may differ from the file edited. Do not dispatch overlapping runs. A trailing pending test can leave the live frame blank; inspect a retained snapshot of an executed command before concluding that app content is absent.

## Maintain the skills

[`.agents/cypress-skills.json`](../../.agents/cypress-skills.json) pins the official toolkit revision and skill versions. Preserve the upstream skill text, referenced files and each copied MIT license. Update all four skill directories in `.agents/skills/`, their `.claude/skills/` entry points and their manifest together, then run `task test:taskfiles`.

This integration uses local Tap and introduces no Cloud connection. [Cypress AI Skills](https://docs.cypress.io/app/tooling/ai-skills) describes the separate Cloud workflow. The source investigation and installation rationale are in [Cypress Tap research](../reports/cypress-tap.md).

## Related documents

- [Testing](../conventions/testing.md)
- [Cypress Tap research](../reports/cypress-tap.md)
- [Workflows](readme.md)
