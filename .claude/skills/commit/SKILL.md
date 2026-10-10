---
name: commit
description: Commit MediLab changes following the Git conventions. Branches off main when needed, stages only the files of the change, writes a `[<type>] <title>` message without attribution lines and pushes. Use when the user runs /commit or asks to commit, save or push changes.
---

# Commit

Follow [.agent/skills/commit/SKILL.md](../../../.agent/skills/commit/SKILL.md).

In Claude Code:

- The hook in `.claude/settings.json` blocks a commit whose title or attribution breaks the rules; fix the message instead of working around the hook.
