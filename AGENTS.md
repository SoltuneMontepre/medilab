# AGENTS.md

Always read [docs/readme.md](docs/readme.md) first to understand the conventions and what you are working on, then follow the conventions it links to before adding or changing anything here.

## Repository

- `docs/` is the documentation. Its index is [docs/readme.md](docs/readme.md).
- Documents describe what the system should do. They are not a description of existing code.

## Hard Rules

- **Read first.** Read the current state of the files before changing anything; they may have changed since you last saw them.
- **Keep docs current.** When a change makes a document outdated, update the document in the same change.
- **Separate concerns.** Split large Python files and models with many fields.
- **No guessing.** Ask the owner. For an unknown requirement, add it to the document's **Open questions**.
- **No silent changes.** State any design choice the owner did not give, in your reply.
- **No leftovers.** Replace old code, requirements and diagrams instead of commenting them out or noting what they used to be. Git history and commit messages explain changes.
- **Comment sparingly.** Only comment "what does this do?" if it is not obvious from the code itself. Do not comment on every line of code, only at the start of a block/function/class.
- **No obvious additions.** Do not add descriptions, labels or explanations that the name or context already makes clear, such as "(database viewer)" after CloudBeaver, in code, scripts, output messages or documents.
- **No session details.** Leave out notes tied to the current work, such as idea numbers or obvious qualifiers like "(one-time)".
