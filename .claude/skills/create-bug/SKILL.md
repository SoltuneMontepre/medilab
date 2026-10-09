---
name: create-bug
description: Turn a defect report into a GitHub bug issue for MediLab. Finds the document rule the behaviour breaks, checks for duplicates, reproduces it locally when possible, drafts the issue from the bug template, asks who to assign, then creates it. Use when the user runs /create-bug or asks to report, file or log a bug or defect.
---

# Create bug

Follow [.agent/skills/create-bug/SKILL.md](../../../.agent/skills/create-bug/SKILL.md).

In Claude Code:

- Reproduce in the built-in browser at `http://localhost:8069` when the app is running, and attach what you saw.
- Write the draft body to the scratchpad directory.
- Ask who to assign with AskUserQuestion in one call with two multi-select questions, since a question holds four options: the first offers `hatohui`, `HuyDG160205`, `KietPham-VN` and `nnh53`, the second `hzanhle` and Nobody. Label each person with their login and name.
