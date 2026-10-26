# Cypress Tap and AI Skills

## Verified capabilities

Cypress Tap ships with Cypress 15.21.0 and later and attaches to `cypress open`. It supports Electron, Chrome, Chromium and Edge. It does not attach to headless `cypress run`, and does not require Cypress Cloud. Tap is beta, so command details should be checked with the installed CLI's `--help`. [Cypress Tap guide](https://docs.cypress.io/app/tooling/cypress-tap)

The commands cover session discovery, spec selection, asynchronous execution, results, command details and historical snapshots. `status --json` exposes run identity and counts; an exit code of zero alone does not establish that a spec passed. [CLI reference](https://docs.cypress.io/app/tooling/cypress-tap)

The official toolkit separates authoring, explanation, documentation lookup and live debugging into `cypress-author`, `cypress-explain`, `cypress-docs` and `cypress-tap`. Its Cloud CLI skill has separate authentication and service requirements. Manual installation can target one project. [Cypress AI Skills](https://docs.cypress.io/app/tooling/ai-skills)

## Source and installation

Use the four local skills from the immutable toolkit revision [`5258ece52a0010d268946e08606c98784c98f255`](https://github.com/cypress-io/ai-toolkit/tree/5258ece52a0010d268946e08606c98784c98f255/skills), including each skill's referenced files. Keep the upstream [MIT license](https://github.com/cypress-io/ai-toolkit/blob/5258ece52a0010d268946e08606c98784c98f255/LICENSE) with copies. Its copyright and permission notice must accompany substantial copies.

The skills CLI supports project installs, agent selection and copying instead of symlinks. Its agent table uses `.agents/skills/` for Codex and Cursor and `.claude/skills/` for Claude Code. [Installation options](https://github.com/vercel-labs/skills/blob/main/docs/commands.md#skills-add), [agent paths](https://github.com/vercel-labs/skills/blob/main/docs/agents.md)

Cursor also documents native project discovery from `.agents/skills/` and `.cursor/skills/`, plus compatibility with `.claude/skills/`. Client discovery should be verified after setup. [Cursor skill directories](https://cursor.com/docs/skills#skill-directories)

Recommended integration: keep the source revision and file provenance reviewable, use project-local discovery, and install no Cloud connection as part of the local Tap workflow. Repository guidance should point agents to the browser-testing conventions and the upstream skills rather than duplicating their full instructions.

## Session and verdict rules

The official [session lifecycle reference](https://github.com/cypress-io/ai-toolkit/blob/5258ece52a0010d268946e08606c98784c98f255/skills/cypress-tap/references/session-lifecycle.md) documents a fallback to another live session when no project matches. Therefore resolve the intended `src/tests` project and bind its discovered PID with `--session` on subsequent calls.

For an explicit run, capture a valid baseline, dispatch one listed spec, and require its expected path, a changed nonempty `startedAt`, and a terminal verdict. Inspect the passed/failed counts and bound the wait. A first-selection build failure needs the reference's separate evidence rule. Empty or partial payloads are not a fresh run. [Upstream verdict contract](https://github.com/cypress-io/ai-toolkit/blob/5258ece52a0010d268946e08606c98784c98f255/skills/cypress-tap/SKILL.md)

Use reporter and command IDs returned by the session, keep app reads bounded, and clear a pin after inspecting its historical snapshot. A watcher rerun or manual UI interaction can change the same session. [Reading the app](https://github.com/cypress-io/ai-toolkit/blob/5258ece52a0010d268946e08606c98784c98f255/skills/cypress-tap/references/reading-the-app.md)

## Validation

Validate local command discovery and missing-session handling, then demonstrate a fresh run against the worktree's own open session. Inspect its reporter and a retained DOM or accessibility snapshot. Exercise stale verdicts, wrong-project sessions and timeouts when implementing a polling wrapper. Keep the existing headless suite as the CI check; a successful Tap dispatch is not test evidence. Windows behavior requires a native validation run; the Tap guide specifies no distinct Windows mode.

## Related documents

- [Testing conventions](../conventions/testing.md)
- [Reports](readme.md)
