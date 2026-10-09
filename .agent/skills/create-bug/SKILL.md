---
name: create-bug
description: Turn a defect report into a GitHub bug issue for MediLab. Finds the document rule the behaviour breaks, checks for duplicates, reproduces it locally when possible, drafts the issue from the bug template, asks who to assign, then creates it. Use for /create-bug or when asked to report, file or log a bug or defect.
---

# Create bug

Read [AGENTS.md](../../../AGENTS.md) and the docs index first, then follow [docs/workflows/reporting-bug.md](../../../docs/workflows/reporting-bug.md) step by step.

- Ask for whatever the report lacks: what happened, the steps, what was expected, where it happened.
- A bug breaks a rule the documents state. When no document says what should happen, report it as a gap in the documents instead of a bug.
- Write the draft body to a temporary file, then show the owner the title, the rule it breaks and a short summary.
- Ask who to assign in a plain message listing every person in the People table of [creating-issue.md](../../../docs/workflows/creating-issue.md#people). Accept several people or nobody.
- Create the issue only after the owner has answered, and reply with its link.
