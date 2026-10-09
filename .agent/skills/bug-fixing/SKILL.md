---
name: bug-fixing
description: Fix the lowest-numbered open MediLab bug issue: reproduce it, prove it with a failing test, fix the cause, check it in the browser and open its pull request. Use for /bug-fixing or when asked to fix the next bug. A bug number given by the user replaces the lowest one.
---

# Bug fixing

Read [AGENTS.md](../../../AGENTS.md) and the docs index first; they override anything here. Then follow [docs/workflows/fixing-bug.md](../../../docs/workflows/fixing-bug.md) step by step.

- Take the bug number the user gives, otherwise the lowest open bug without an open pull request. Say which bug you picked before changing anything.
- Do not change code before the bug is reproduced and a test fails because of it.
- Fix the cause, not the symptom. Ask the owner when the documents do not say what should happen, and record what stays open in `questions/<topic>.md`.
- Sign in to the local app only with the local development account from the project's configuration; never with real credentials.
- Commits and the pull request carry no co-author or attribution lines.
- Finish with the pull request link, the cause, and the tests and browser checks that passed.
