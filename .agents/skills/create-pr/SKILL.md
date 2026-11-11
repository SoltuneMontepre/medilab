---
name: create-pr
description: Open a MediLab pull request for the current change and see it through the pipelines and SonarQube. Branches off main, commits with the commit skill, titles the pull request per the Git conventions without attribution lines, then waits for the pipelines and fixes what SonarQube reports. Use for /create-pr or when asked to create, open or raise a pull request or PR.
---

# Create pull request

Read [AGENTS.md](../../../AGENTS.md) and the docs index first; they override anything here. Then follow [docs/workflows/creating-pr.md](../../../docs/workflows/creating-pr.md) step by step.

- Put the change on its own branch off `main`, named as [Git](../../../docs/conventions/git.md#branch-names) says, and commit it with the [commit skill](../commit/SKILL.md). Never include the owner's unrelated changes.
- Title the pull request as [Git](../../../docs/conventions/git.md#pull-request-titles) says: `[<type>] <title>`, or `[<type>] | #<issue> <title>` for an issue.
- The body summarises what changed and what was tested, contains `Closes #<issue>` when there is an issue, and carries no co-author or attribution lines.
- After opening it, wait for every pipeline and check SonarQube as the workflow says; fix, push and repeat until both pass.
- Reply with the pull request link, which pipelines passed, the quality gate and issue count, and the design choices the owner did not give.
