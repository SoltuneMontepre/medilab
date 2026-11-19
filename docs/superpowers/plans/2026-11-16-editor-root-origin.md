# Editor Origin-Root Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Sync refuse editor handoffs to configured Odoo URLs with a path prefix, because the editor page and its login/assets use origin-root paths.

**Architecture:** Keep path-prefix support for the Sync API unchanged. Validate the configured URL specifically at the editor handoff boundary, permit an origin with an optional trailing slash, and show an explicit refusal for a non-root path. Record the support boundary in the architecture decision, editor specification, Sync functional document, and resolved question.

**Tech Stack:** Rust, `url::Url`, Cargo unit tests, Markdown documentation.

**Spec:** `docs/specs/laboratory-files.md` (online editing and Sync handoff); current issue #230.

## Global Constraints

- Editor page path is `/medilab/laboratory-files/<file_id>/edit` at the origin root.
- No caller-supplied path prefix, query, fragment, credentials, or unsafe URL components may be trusted.
- The Sync API's configured base-path behavior remains unchanged.
- Do not claim native Desktop or staging acceptance from this local URL-validation test.

## Review Focus

- Empty and trailing-slash origin-root URLs still open the editor.
- Any non-root URL path is refused before invoking the opener.
- Query strings, fragments, credentials, and unsafe components remain refused by existing validation.
- Existing Sync API endpoints continue to accept a configured path prefix.
- The error states the actual origin-root-only limitation without implying editor load/save success.

### Task 1: Enforce and document origin-root-only editor handoff

**Files:**
- Modify: `src/applications/medilab-sync/src-tauri/src/browser.rs`
- Test: `src/applications/medilab-sync/src-tauri/src/browser.rs`
- Create: `docs/decisions/editor-deployment-base-paths.md`
- Modify: `docs/decisions/readme.md`
- Modify: `docs/specs/laboratory-files.md`
- Modify: `docs/functional/laboratory_module/applications/medilab-sync.md`
- Modify: `questions/laboratory.md`

**Interfaces:**
- Consumes: existing `server_url::endpoint(base, path)` validation and editor `open_editor_with(base, file_id, open)`.
- Produces: editor-specific root-origin validation; general endpoint joining remains prefix-capable.

- [x] Add a Rust unit test proving `/odoo/` is refused before the opener is called; verify the test fails against current behavior.
- [x] Implement editor-specific path validation. Permit empty/root path only; do not change generic API endpoint joining.
- [x] Confirm the origin-root and trailing-slash handoffs still pass, and existing unsafe URL/id and opener-retry tests remain green.
- [x] Record the decision, update the spec and Sync functional description, and remove the now-answered base-path question.
- [x] Run Rust formatting and Sync application checks; inspect the diff and commit only these files.
