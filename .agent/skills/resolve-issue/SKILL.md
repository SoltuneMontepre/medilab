---
name: resolve-issue
description: Implement the lowest-numbered open MediLab GitHub issue from the docs, test it, check it in the browser and open its pull request. Use for /resolve-issue or when asked to pick up, work on or resolve the next issue. An issue number given by the user replaces the lowest one.
---

# Resolve issue

Read [AGENTS.md](../../../AGENTS.md) and the docs index first; they override anything here. Then follow [docs/workflows/resolving-issue.md](../../../docs/workflows/resolving-issue.md) step by step.

- Take the issue number the user gives, otherwise the lowest open issue without an open pull request. Say which issue you picked before changing anything.
- Read the issue's spec when it links one, and the questions file of its topic only.
- When a Trello connection is available, search the medilab board for cards about the feature. Confirm with the owner before building anything a card adds that the documents do not say.
- Use what your environment offers: search tools or sub-agents for wide codebase searches, a browser for the check at `http://localhost:8069`, code review before the pull request, and the SonarQube and pull request tools for [Creating a pull request](../../../docs/workflows/creating-pr.md).
- Sign in to the local app only with the local development account from the project's configuration; never with real credentials.
- Ask the owner when the documents do not answer something, record what stays open in `questions/<topic>.md` with the story IDs it blocks, and do not guess.
- Commits and the pull request carry no co-author or attribution lines.
- Finish with the pull request link, the tests and browser checks that passed, the design choices the owner did not give, and the questions added.
