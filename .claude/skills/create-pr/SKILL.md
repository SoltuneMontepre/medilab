---
name: create-pr
description: Open a MediLab pull request for the current change and see it through the pipelines and SonarQube. Branches off main, commits with the commit skill, titles the pull request per the Git conventions without attribution lines, then waits for the pipelines and fixes what SonarQube reports. Use when the user runs /create-pr or asks to create, open or raise a pull request or PR.
---

# Create pull request

Follow [.agents/skills/create-pr/SKILL.md](../../../.agents/skills/create-pr/SKILL.md).

In Claude Code:

- Write the pull request body to the scratchpad directory and pass it with `--body-file`.
- After opening the pull request, bind it with the pull request tools and read its checks from there instead of polling; use the SonarQube tools for the quality gate.
- Do not sync the branch with its base when it falls behind `main`, only when it conflicts; the merge queue tests it on the latest `main`.
- The hook in `.claude/settings.json` blocks a title or body that breaks the rules; fix them instead of working around the hook.
