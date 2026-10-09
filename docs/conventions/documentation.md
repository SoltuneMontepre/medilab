# Documentation conventions

How documents in `docs/` are written and formatted. These rules apply to people and agents alike.

## Writing rules

- **Language.** English. Domain terms are defined once and used consistently.
- **Target design, not current code.** The system is being rebuilt. Describe what the system should do, not what the existing implementation does. Do not carry over legacy names, states, field names or limitations unless asked.
- **Do not guess.** Do not invent behaviour, dependencies or module boundaries to fill a gap. Where the owner has not decided, add the question to `questions/<topic>.md` at the repository root instead of choosing silently, ending with the user story or shared requirement IDs it blocks, such as `(blocks US-AD13)` or `(blocks SH-05)`. Documents do not contain open questions. When you make a design choice the owner did not state, say so in your reply so it can be checked.
- **Say what was and was not checked.** Report what you read and ran. Do not claim a diagram renders, a link works or a behaviour is verified unless you checked it.
- **Stay in scope.** A module document says only what belongs to that module. The module split and each module's purpose are described once, in [functional/index.md](../functional/index.md). Requirements shared by all modules live in [functional/shared.md](../functional/shared.md).

## Indexes

Each folder in `docs/` has an index (`readme.md`, or `functional/index.md`) that lists every document in it with a one-line summary. `docs/readme.md` links only to these indexes. When you add, rename or remove a document, update the index of its folder in the same change.

## Module documents

Each module has an overview and one feature document per actor:

```text
functional/<module>/overview.md
functional/<module>/features/<actor>.md
```

The overview explains the module and links to the actor documents.

## Document format

- One topic per file; the first line is `# Title`.
- User stories use IDs and the form "As a <actor>, I want <goal>, so that <benefit>": `US-C` customer, `US-S` sales, `US-A` accountant, `US-AD` administrator, `US-SC` sample collector, `US-SR` sample receiver, `US-T` tester, `US-HD` head of department, `US-LH` lab head, `US-SUB` subcontractor. Keep IDs in order; when stories are added or removed, renumber them and update every anchor that refers to them.
- Each feature has rules in a table, acceptance criteria as a list, and a state diagram when something has states.
- Shared requirements use `SH-nn` IDs and are referred to by ID from module documents.
- Diagrams are Mermaid in fenced code blocks.
- End a document with **Related documents**.
- Use relative links, and check them after moving or renaming a file.
