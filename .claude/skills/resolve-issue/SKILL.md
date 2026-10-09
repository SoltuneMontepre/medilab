---
name: resolve-issue
description: Implement the lowest-numbered open MediLab GitHub issue from the docs, test it, check it in the browser and open its pull request. Use when the user runs /resolve-issue or asks to pick up, work on or resolve the next issue. An issue number given by the user replaces the lowest one.
---

# Resolve issue

Follow [.agent/skills/resolve-issue/SKILL.md](../../../.agent/skills/resolve-issue/SKILL.md).

In Claude Code:

- Search Trello with the Trello search tool when it is connected; load it with tool search first.
- Use the Explore agent for wide codebase searches; read the files you change yourself.
- Check the interface in the built-in browser: open `http://localhost:8069` with the preview or navigate tool, and read the page text or take screenshots for each acceptance criterion.
- Run the code review and simplify skills on the finished change before opening the pull request.
- After opening the pull request, bind it with the pull request tools and read its checks from there instead of polling; use the SonarQube tools for the quality gate.
