---
name: create-issue
description: Turn a feature from the MediLab functional documents into a GitHub feature issue. Finds the stories that are not started and ready, checks for existing issues, code, blocking questions and specs, drafts the issue from the feature template, asks who to assign, then creates it. Use for /create-issue or when asked to create, open or file an issue or ticket for a documented feature.
---

# Create issue

Read [AGENTS.md](../../../AGENTS.md) and the docs index first, then follow [docs/workflows/creating-issue.md](../../../docs/workflows/creating-issue.md) step by step.

- Work out story status from GitHub and readiness from the documents, as the workflow says. Never write status into the documents.
- When a Trello connection is available, search the medilab board for cards about the feature, as the workflow's Trello section says.
- When the user names no feature, list the stories that are not started and ready, grouped by feature, and ask which one.
- Report the status check before drafting. Stop and ask when the feature is already covered, not ready, or needs a spec that does not exist.
- Write the draft body to a temporary file, then show the owner the title, the stories and a short summary.
- Ask who to assign with your tool's selection prompt when it has one, so the owner picks instead of typing; otherwise as a lettered list the owner answers with letters, such as "A, C": A to E for the people in the People table of [creating-issue.md](../../../docs/workflows/creating-issue.md#people), each with their login and name, and F for nobody.
- Create the issue only after the owner has answered, and reply with its link.
