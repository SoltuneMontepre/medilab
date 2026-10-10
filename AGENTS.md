# AGENTS.md

Always read [docs/readme.md](docs/readme.md) first to understand the conventions and what you are working on, then follow the conventions it links to before adding or changing anything here.

## Repository

- `docs/` is the documentation. Its index is [docs/readme.md](docs/readme.md).
- Documents describe what the system should do. They are not a description of existing code.
- `questions/` holds the owner's open questions, one file per topic: `questions/<topic>.md`.

## MCP servers

`.mcp.json` configures these servers; `task ai:setup` installs what they need. Use them whenever the task calls for them, before falling back to the shell:

| Server      | Use it to                                                                                              |
| ----------- | ------------------------------------------------------------------------------------------------------ |
| `serena`    | Find symbols, references and definitions in the modules, and edit code by symbol, instead of grepping. |
| `postgres`  | Query the local database to check records, schema and constraints after an install or upgrade.        |
| `context7`  | Read current documentation of Odoo and other libraries before relying on an API.                       |
| `sonarqube` | Read the quality gate and issues of a branch or pull request, and fix what it reports.                 |
| `doppler`   | Look up which secrets and configs exist. Never print a secret's value.                                 |

When a server is not connected, say so, then continue with the shell.

## Hard Rules

- **Read first.** Read the current state of the files before changing anything; they may have changed since you last saw them.
- **Keep docs current.** When a change makes a document outdated, update the document in the same change.
- **Separate concerns.** Split large Python files and models with many fields.
- **No guessing.** Ask the owner. For an unknown requirement, add it to `questions/<topic>.md`. Read a questions file only when working on its topic.
- **No silent changes.** State any design choice the owner did not give, in your reply.
- **No leftovers.** Replace old code, requirements and diagrams instead of commenting them out or noting what they used to be. Git history and commit messages explain changes.
- **Comment sparingly.** Only comment "what does this do?" if it is not obvious from the code itself. Do not comment on every line of code, only at the start of a block/function/class. Models are the exception: each model class has a comment with its Vietnamese term, or for a link model what it links for, and each field has a comment saying what data it holds.
- **No obvious additions.** Do not add descriptions, labels or explanations that the name or context already makes clear, such as "(database viewer)" after CloudBeaver, in code, scripts, output messages or documents.
- **No co-author trailers.** Do not add `Co-Authored-By` or other attribution lines to commit messages or pull request descriptions.
- **Ship permissions.** Every new document model ships its permission records; see [Module structure](docs/conventions/module_structure.md#permissions).
- **No session details.** Leave out notes tied to the current work, such as idea numbers or obvious qualifiers like "(one-time)".
