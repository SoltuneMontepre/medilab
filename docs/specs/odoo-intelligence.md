# Odoo intelligence

## Goal

Claude Code, Codex CLI, Cursor editor and Cursor Agent should resolve Odoo models and fields against the same pinned Odoo Community source and the addons in their current worktree. [Issue #104](https://github.com/SoltuneMontepre/medilab/issues/104) tracks delivery.

## Design

Use official OdooLS 1.6.0 for Python and XML intelligence. Download the server and its matching typeshed from the official release, verify SHA-256 digests, and install into a versioned directory inside `.local/odoo-intelligence`. Keep Odoo source at the repository's pinned Odoo 20 revision in a separate tooling mirror, including all Community addons. This mirror must not alter the source used by Pyright.

Expose definition, references, hover, completion, document symbols and published diagnostics through a read-only stdio MCP server. Requests use relative paths and zero-based UTF-16 positions. Reject paths outside the worktree and unsupported requests. The bridge must wait for indexing, handle OdooLS client requests, bound response waits, return server errors honestly, and stop only its own child process on disconnect. Diagnostics include freshness information; an empty or unavailable diagnostic response is not a clean validation result.

Configure the bridge as project tooling for Claude Code, Codex and Cursor Agent. Native LSP is optional for Claude Code; MCP is the common navigation interface. Use the official Odoo VS Code extension in Cursor's editor. Editor activation and Agent MCP access require separate verification.

Serena should use its built-in Python server alongside TypeScript, Terraform and HTML. It retains symbol search, references and editing rather than routing these through the Odoo adapter, which lacks rename support. Launch a pinned Serena environment locally and retain its Claude hooks. Keep the other MCP definitions intact.

Each worktree owns its Python environment, source mirror and configuration. Each bridge process owns a distinct log directory and disables OdooLS's on-disk file cache. Do not search ancestors for another checkout's binary or addons, use fixed TCP ports, reinstall global tools, or stop other clients. Serialize installation and publish verified downloads atomically. Existing processes may continue using their versioned binaries.

## Verification

Unit tests should cover path containment, Unicode positions, release integrity, framed JSON-RPC, error and timeout propagation, unsupported methods, and process cleanup. Integration checks should launch official OdooLS and assert definition targets in both Odoo core and MediLab addons, field completion, hover, references and XML navigation. MCP protocol tests and independent client tests must report their actual results. Concurrent sessions must resolve the addons of their own roots.

Verification reports distinguish verified, unsupported and unverified functionality. Client configuration or installation does not count as model resolution. Missing credentials, unavailable UI automation and untested platforms remain explicit limitations. Application runtime and database changes are outside this tooling change.

## Related documents

- [Python conventions](../conventions/python.md)
- [Taskfile conventions](../conventions/taskfiles.md)
- [Git conventions](../conventions/git.md)
- [OdooLS release](https://github.com/odoo/odoo-ls/releases/tag/1.6.0)
