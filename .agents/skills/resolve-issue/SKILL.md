---
name: resolve-issue
description: Implement the lowest-numbered open MediLab GitHub issue from the docs, test it, check it in the browser and open its pull request. Use for /resolve-issue or when asked to pick up, work on or resolve the next issue. An issue number given by the user replaces the lowest one.
---

# Resolve issue

Read [AGENTS.md](../../../AGENTS.md) and the docs index first; they override anything here. Then follow [docs/workflows/resolving-issue.md](../../../docs/workflows/resolving-issue.md) step by step.

- Take the issue number the user gives, otherwise the lowest open issue without an open pull request and not assigned to someone else, who may already be working on it.
- Assign yourself to the issue first, before reading the code or changing anything, then say which issue you picked. When the user gives an issue assigned to someone else, ask before taking it over.
- Read the issue's spec when it links one, and the questions file of its topic only.
- Use what your environment offers: search tools or sub-agents for wide codebase searches, a browser for the check at `http://localhost:8069`, code review before the pull request, and the SonarQube and pull request tools for [Creating a pull request](../../../docs/workflows/creating-pr.md).
- The pull request merges through the merge queue once it is approved, with **Merge when ready**, as [Git](../../../docs/conventions/git.md#merging) says. Do not update the branch with `main` by hand unless it conflicts. Stacked pull requests (`gh stack`) are only for sub-issues joined by **blocked by**.
- Sign in to the local app only with the local development account from the project's configuration; never with real credentials.
- Ask the owner when the documents do not answer something, record what stays open in `questions/<topic>.md` with the story IDs it blocks, and do not guess.
- Commits and the pull request carry no co-author or attribution lines.
- Finish with the pull request link, the tests and browser checks that passed, the design choices the owner did not give, the questions added, and the issues unblocked.
