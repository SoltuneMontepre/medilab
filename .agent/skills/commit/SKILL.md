---
name: commit
description: Commit MediLab changes following the Git conventions. Branches off main when needed, stages only the files of the change, writes a `[<type>] <title>` message without attribution lines and pushes. Use for /commit or when asked to commit, save or push changes.
---

# Commit

Read [AGENTS.md](../../../AGENTS.md) and the docs index first; they override anything here. Then follow [docs/conventions/git.md](../../../docs/conventions/git.md).

- Read `git status` and the diff before staging. Stage only the files of the change; leave the owner's other changes unstaged and say which ones you left.
- On `main`, create a branch named as [Git](../../../docs/conventions/git.md#branch-names) says before committing.
- Update every document the change makes outdated in the same commit.
- Write the title as `[<type>] <title>`, with `| #<issue>` when the change belongs to an issue. Say what the change does; leave out session details such as poll results or idea numbers.
- Commits carry no co-author or attribution lines.
- Amend or force-push only a branch nobody else works on, and only with `--force-with-lease`.
- Reply with the branch, the commit title and the files left unstaged.
