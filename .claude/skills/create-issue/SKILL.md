---
name: create-issue
description: Turn a feature from the MediLab functional documents into a GitHub feature issue. Finds the stories that are not started and ready, checks for existing issues, code, blocking questions and specs, drafts the issue from the feature template, asks who to assign, then creates it. Use when the user runs /create-issue or asks to create, open or file an issue or ticket for a documented feature.
---

# Create issue

Follow [.agents/skills/create-issue/SKILL.md](../../../.agents/skills/create-issue/SKILL.md).

In Claude Code:

- Write the draft body to the scratchpad directory.
- Ask who to assign with AskUserQuestion in one call with two multi-select questions, since a question holds four options: the first offers `hatohui`, `HuyDG160205`, `KietPham-VN` and `nnh53`, the second `hzanhle` and Nobody. Label each person with their login and name.
