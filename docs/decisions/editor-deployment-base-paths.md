# Editor deployment base paths

Selected on 2026-11-16 under the owner's instruction to choose and implement the most viable option for #230.

## Context

The Odoo editor route, login and identity redirects, Retry navigation, and editor assets use origin-root paths. Medilab Sync accepts a configured base path and uses it for the laboratory API. That API behavior does not make the Odoo editor page work below a path prefix: `/odoo/` is already an Odoo application route, and no proxy/application prefix design has been verified for the full browser flow.

## Decision: editor deployments use the origin root

Online editor pages are supported only when Odoo is served at the origin root. Medilab Sync refuses to launch the editor when its configured server URL contains a non-root path, and explains the limitation. The Sync API continues to support configured base paths.

**Rationale.** Origin-root editor behavior has local HTTP/browser evidence. Reusing a configured prefix without matching behavior in login, redirects, assets, cookies and security headers would open a URL that cannot complete the editor flow. A dedicated proxy/application prefix design is not selected because it requires deployment-specific routing and security review that the existing implementation does not provide.

### Requirements

| ID | Priority | Requirement |
| --- | --- | --- |
| EDT-13 | P1 | Supported editor installations serve Odoo at the origin root. Sync refuses an editor handoff to a configured path prefix with a visible explanation. Sync API path-prefix behavior is unchanged. |

## What this decision does not decide

This does not establish a native installed-Desktop pilot, pinned Document Server acceptance, staging ingress or recovery evidence, or production readiness. Supporting prefixed editor deployments requires a later decision and a separately reviewed, tested proxy/application design.

## Related documents

- [Laboratory files specification](../specs/laboratory-files.md#desktop-handoff-and-deployment-paths)
- [Medilab Sync](../functional/laboratory_module/applications/medilab-sync.md)
- [Laboratory questions](../../questions/laboratory.md)
