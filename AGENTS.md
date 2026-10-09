# AGENTS.md

Always read [docs/readme.md](docs/readme.md) first to understand the conventions and what you are working on, then follow the conventions it links to before adding or changing anything here.

## Repository

- `docs/` is the documentation. Its index is [docs/readme.md](docs/readme.md).
- Documents describe what the system should do. They are not a description of existing code.
- `questions/` holds the owner's open questions, one file per topic: `questions/<topic>.md`.

## Commands

The owner runs these by name, such as `/create-issue`. Each is a skill in `.agent/skills/<command>/SKILL.md` that follows a workflow in [docs/workflows](docs/workflows/readme.md); Claude Code and Cursor load them from `.claude/skills/` and `.cursor/commands/`.

- `create-issue`: turn a documented feature into a GitHub feature issue ([creating an issue](docs/workflows/creating-issue.md))
- `resolve-issue`: implement the lowest open issue and open its pull request ([resolving an issue](docs/workflows/resolving-issue.md))

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
- **No session details.** Leave out notes tied to the current work, such as idea numbers or obvious qualifiers like "(one-time)".
