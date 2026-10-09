# Fixing a bug

How an open bug issue is fixed, proven by a test and opened as a pull request.

## Steps

1. **Pick the bug.** Take the open issue of type Bug with the lowest number that has no open pull request: `gh issue list --state open --label bug --json number,title --jq 'sort_by(.number)'`. Tell the owner which bug is being worked on.
2. **Read.** [AGENTS.md](../../AGENTS.md), the [docs index](../readme.md) and its conventions, the issue, the document rule it links as expected behaviour, and the code involved.
3. **Branch** from an up-to-date `main`: `fix/<issue number>-<short-description>`, following [Git](../conventions/git.md).
4. **Reproduce it.** Follow the issue's steps on the local app (`task up`, `task upgrade MODULES=<module>`). If it does not reproduce, report what was tried and stop.
5. **Write a failing test** that shows the bug ([testing](../conventions/testing.md)), and run it to see it fail.
6. **Find the cause.** Fix the cause, not the symptom. When the cause is a gap or a contradiction in the documents, ask the owner and record what stays open in `questions/<topic>.md`.
7. **Fix it.** Run the new test and `task lint`, `task typecheck` and `task test:core`; all pass.
8. **Check in the browser** that the issue's steps now give the expected behaviour, and that the screens around the change still work.
9. **Open the pull request.**
   - Commit and push. The title follows [Git](../conventions/git.md): `[fix] | #<issue number> <title>`.
   - The body states the cause, the fix, `Closes #<issue number>`, and what was tested.
   - Then follow [Creating a pull request](creating-pr.md) until the pipelines pass and SonarQube reports no issue.
10. Reply with the pull request link, the cause, and what was checked.

## Related documents

- [Reporting a bug](reporting-bug.md)
- [Creating a pull request](creating-pr.md)
- [Testing](../conventions/testing.md)
