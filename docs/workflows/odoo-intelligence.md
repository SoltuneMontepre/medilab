# Odoo intelligence

## Installation

Run from the checkout or Git worktree you want the clients to use:

```sh
task ai:setup
task ai:test
task ai:verify
```

Setup requires Git, uv and Node.js with npx. It creates the locked Python 3.13 environment in `tools/odoo-intelligence/.venv`, installs official OdooLS 1.6.0 with its matching typeshed, and fetches the repository-pinned Odoo 20 source. Release checksums are recorded in `tools/odoo-intelligence/odoo_intelligence/release.json` and checked before extraction. Terraform 1.15.8, matching `infra/terraform.tf`, is installed locally for Serena's Terraform server. Setup does not replace global tools, edit global client settings, initialize Terraform or change a database.

The Odoo mirror lives in `.local/odoo-intelligence/odoo-source`. It includes all Community addons, internal Odoo addons and the five MediLab addons under `src/core/modules`. It is separate from `.local/odoo-source`, which `task dev:odoo-source` prepares for Pyright. An incomplete or mismatched tooling mirror must be moved aside before reinstalling; setup does not overwrite it.

Open the worktree root as the editor workspace. `odools.toml` supplies the same default profile to the MCP bridge and the official Odoo extension. JavaScript processing is disabled in OdooLS; existing TypeScript services handle it.

## Architecture

```mermaid
flowchart LR
    Claude[Claude Code] --> MCP[Odoo MCP]
    Codex[Codex CLI] --> MCP
    Agent[Cursor Agent] --> MCP
    MCP --> LS[Official OdooLS]
    Editor[Cursor editor] --> Extension[Official Odoo extension]
    Extension --> Native[Bundled OdooLS]
    LS --> Config[Worktree odools.toml]
    Native --> Config
    Config --> Core[Pinned Odoo source]
    Config --> Addons[Current MediLab addons]
    Clients[Coding clients] --> Serena[Serena]
    Serena --> Generic[Python / TypeScript / Terraform / HTML]
```

The read-only Odoo MCP server exposes `definition`, `references`, `hover`, `completion`, `document_symbols`, `diagnostics` and `status`. Paths are relative to the worktree; line and character positions are zero-based, with characters counted as UTF-16 code units. It rejects paths that escape the checkout, including symlinks. Results include file URIs and source ranges from OdooLS.

Serena uses its built-in `python` server and retains its other language servers and editing tools. Use Odoo MCP for framework model strings, inherited fields and XML navigation; use Serena for general symbol search and edits. OdooLS has no rename support, so rename is not exposed by the bridge. The bridge also avoids unsupported pull-diagnostic requests and reads published diagnostics with freshness metadata instead. An unavailable or stale diagnostic report is not a clean validation result.

Each bridge owns a stdio OdooLS process and a distinct log directory. It waits for indexing, synchronizes queried files from disk and sends file-change notifications for the current checkout's Python/XML addons before subsequent navigation. It has no fixed TCP port. On-disk OdooLS file caching is disabled. Changes in unsaved editor buffers belong to the native editor session; MCP reads saved files.

Blocking LSP operations run in worker threads so MCP cancellation and disconnect can be handled during indexing. Cancellation stops this session's owned child; a subsequent query can initialize it again. Diagnostic document versions are checked when provided, with timestamps used only as a fallback.

## Clients

| Client | Project configuration | Navigation interface |
| --- | --- | --- |
| Claude Code | `.mcp.json`, `.claude/settings.json` | Odoo MCP; local Serena and its existing hooks |
| Codex CLI | `.codex/config.toml` | Odoo MCP and local Serena |
| Cursor Agent | `.cursor/mcp.json` | Odoo MCP and local Serena |
| Cursor editor | `odools.toml`, `.vscode/settings.json` | Official `Odoo.odoo` extension |

Start a new session after setup; existing agents keep their processes and configurations. Cursor's project configuration also holds the Doppler, SonarQube, Postgres and Context7 servers of `.mcp.json`. Codex's project configuration holds only Odoo and Serena and leaves global MCP definitions alone.

### Claude Code

Launch `claude` from the worktree root. Project MCP servers are enabled by the existing project settings. Check `claude mcp get odoo`, then request an Odoo-aware definition or hover. For a concrete check, resolve the model string `medilab.reconciliation.day` in `src/core/modules/sol_commerce/models/invoicing/payment_transaction.py`; it should lead to the `ReconciliationDay` class. `tools/odoo-intelligence/odoo_intelligence/navigation_cases.json` lists the source text and expected target of every case that `task ai:verify` and the Cursor probe check.

The Serena hooks run through the locked local environment.

### Codex CLI

Trust the specific worktree when Codex asks so it can load `.codex/config.toml`. Check `codex mcp get odoo --json` and use `/mcp` in a new session. Project configuration is ignored in untrusted checkouts. Launching from a subdirectory is supported: the launcher finds the nearest checkout containing `tools/odoo-intelligence/run.py`, and the package binds the server to that checkout.

For a noninteractive check without persisting trust globally, supply the worktree trust as a CLI override:

```sh
codex -c 'projects."/absolute/path/to/worktree".trust_level="trusted"' mcp get odoo --json
```

Do not use `--ignore-user-config` when checking this project configuration; it changes how Codex loads configuration.

### Cursor Agent

Launch a new Agent from the worktree and approve the project MCP servers. Ask it to use the `odoo` definition and hover tools. Cursor Agent CLI does not expand `${workspaceFolder}` in MCP arguments, so the launcher discovers the checkout from its working directory.

Use normal agent mode: Ask mode refuses MCP tool calls, even read-only ones. `--approve-mcps` approves server connections; it does not guarantee that Ask mode will allow tool execution. For a controlled headless verification, `--print --force --approve-mcps` permits the requested calls; keep the prompt restricted to the read-only Odoo tools. This is a session setting and does not replace normal interactive approvals.

### Cursor editor

The repository recommends the official `Odoo.odoo` extension. For a separate profile that leaves existing editor sessions alone:

```sh
task ai:cursor-setup
cursor --new-window --user-data-dir "$PWD/.local/cursor/user-data" --extensions-dir "$PWD/.local/cursor/extensions" "$PWD"
```

The installer downloads the official platform-specific 1.6.0 VSIX, verifies its checksum, and installs it into this worktree's profile. It bundles its own matching OdooLS and typeshed. The extension requires a VS Code API version of at least 1.125.0. Pylance, formatters and JavaScript services remain configured. Workspace settings suppress the extension's offers to disable Python/JavaScript services.

## Verification

`task ai:verify` writes `.local/verification/mcp-navigation.json`: the asserted definitions, relation hover, field completion, references, document symbols and diagnostic freshness. `task ai:test` includes framed JSON-RPC, path and archive safety, error/timeout propagation, a references crash regression and concurrent-worktree tests. Live tests report skips when OdooLS is absent; inspect the summary before claiming integration passed.

For the native Cursor check, install the isolated profile and run:

```sh
cursor --new-window --classic --user-data-dir "$PWD/.local/cursor/user-data" --extensions-dir "$PWD/.local/cursor/extensions" --extensionDevelopmentPath="$PWD/tools/odoo-intelligence/tests/cursor" "$PWD"
```

The probe writes `.local/verification/cursor-editor.json`. It quits its test window after recording results, so use this command only with the isolated profile. Inspect `verified`, the definition targets, completion and hover values; installation alone is insufficient.

## Limitations

- Only the navigation cases in `navigation_cases.json` are checked; indexing every manifest does not prove that every dynamic ORM expression resolves.
- No native Odoo LSP plugin is installed for Claude Code or Codex; MCP is their Odoo interface.
- Codex loads the project configuration only in a trusted checkout.
- The installer selects the official Linux, macOS and Windows artifacts, but only Linux x86-64 has been run.
- MCP connectivity and tool schemas do not prove that a client's model-driven calls succeed; check actual tool responses.

## Maintenance and troubleshooting

- **Missing Terraform blocks Serena:** rerun setup, then use the repository's Serena launcher. It prepends the local Terraform directory only to that process's PATH.
- **Missing mirror or release:** run setup in this worktree. A different agent's `.local` directory is not searched automatically.
- **Incorrect root:** call Odoo `status` and compare `workspace` with the intended checkout. Open the worktree root in the editor. Do not combine several different Odoo worktrees in one OdooLS workspace.
- **Index timeout, crashes or empty results:** inspect the directory returned by `status` or the tool error, then check `odools.toml`, the source revision and module dependencies. Restart only this client's MCP session after a crashed server. Empty definitions can indicate unsupported expressions or incomplete analysis.
- **References panic:** OdooLS 1.6.0 can panic with `no text_document provided` when the definition is not open. The MCP bridge opens resolved definition documents before requesting references; its regression test exercises this case. The official native editor server does not use that workaround. Use MCP references when this affects native references.
- **Saved changes:** MCP synchronizes the queried file and watches other Python/XML addons before navigation. For unsaved changes, use the editor's native server or save first. The immutable Odoo mirror is not watched for local edits.
- **Updating releases:** update the version and official asset digests in `odoo_intelligence/release.json`, keep `odoo_revision` and the Terraform version equal to `ODOO_SOURCE_REVISION` in `tools/taskfiles/dev.taskfile.yml` and `required_version` in `infra/terraform.tf` (`task ai:test` checks both), and regenerate `uv.lock` for dependency changes. OdooLS releases use even minor versions for stable releases; prefer stable versions. Rerun all navigation and client checks. Source updates require moving this worktree's old tooling mirror aside, leaving Pyright's mirror intact.

## Related documents

- [Odoo intelligence design](../specs/odoo-intelligence.md)
- [Python conventions](../conventions/python.md)
- [Testing](../conventions/testing.md)
- [Taskfile conventions](../conventions/taskfiles.md)
- [Issue #104](https://github.com/SoltuneMontepre/medilab/issues/104)
- [Official OdooLS release](https://github.com/odoo/odoo-ls/releases/tag/1.6.0)
- [OdooLS configuration](https://github.com/odoo/odoo-ls/wiki/3.-Configuration-files)
- [Official Odoo extension](https://github.com/odoo/odoo-vscode)
- [Claude Code MCP](https://code.claude.com/docs/en/mcp)
- [Codex MCP](https://developers.openai.com/codex/mcp)
- [Cursor MCP](https://cursor.com/docs/mcp)
