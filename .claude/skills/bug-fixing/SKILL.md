---
name: bug-fixing
description: Fix the lowest-numbered open MediLab bug issue: reproduce it, prove it with a failing test, fix the cause, check it in the browser and open its pull request. Use when the user runs /bug-fixing or asks to fix the next bug. A bug number given by the user replaces the lowest one.
---

# Bug fixing

Follow [.agent/skills/bug-fixing/SKILL.md](../../../.agent/skills/bug-fixing/SKILL.md).

In Claude Code:

- Use the debug skill to reproduce, isolate and find the cause.
- Reproduce and check the fix in the built-in browser at `http://localhost:8069`.
- Run the code review skill on the fix before opening the pull request.
- After opening the pull request, bind it with the pull request tools and read its checks from there instead of polling; use the SonarQube tools for the quality gate.
