# Resolving an issue

How an open feature issue is implemented, checked in the browser and opened as a pull request.

## Steps

1. **Pick the issue.** Take the open issue with the lowest number that has no open pull request: `gh issue list --state open --json number,title --jq 'sort_by(.number)'`. Tell the owner which issue is being worked on.
2. **Read before writing.**
   - [AGENTS.md](../../AGENTS.md), the [docs index](../readme.md) and the conventions it links to.
   - The issue, its spec if it has one, and every document, diagram and file it references.
   - `questions/<topic>.md` for the issue's topic only.
   - The Trello cards about the feature, when a Trello connection is available ([Trello](creating-issue.md#trello)).
   - The existing code the issue touches.
3. **Branch** from an up-to-date `main`: `feat/<issue number>-<short-description>`, following [Git](../conventions/git.md).
4. **Plan.** Turn each checklist item and acceptance criterion into the models, views, data and tests to write. Ask the owner when the documents do not answer something; add what stays undecided to `questions/<topic>.md`. Do not guess.
5. **Implement**, following the [module structure](../conventions/module_structure.md), [database](../conventions/database.md), [Python](../conventions/python.md) and [translation and menus](../conventions/translation.md) conventions: one model per file in its concern folder, a `MODEL_*` constant per model, a comment with the Vietnamese term above each model class and a comment above each field, access rules, sequences, views, menus and Vietnamese translations.
6. **Test.** Write a test for each acceptance criterion ([testing](../conventions/testing.md)), then run `task lint`, `task typecheck` and `task test:core`. Fix everything they report.
7. **Check in the browser.**
   - Start the app with `task up`, then `task upgrade MODULES=<module>`.
   - Open `http://localhost:8069` in the browser and sign in with the local development account.
   - Walk through every acceptance criterion in the interface, including that a user without the permission does not see the action.
   - Check the screens in English and Vietnamese. Fix what does not work and test again.
8. **Review.** Review the change for correctness and simplicity, and update every document the change makes outdated, including the [database diagrams](../infrastructure/readme.md).
9. **Open the pull request.**
   - Commit and push. The title follows [Git](../conventions/git.md): `[feat] | #<issue number> <title>`.
   - The body summarises what was built, contains `Closes #<issue number>`, and says what was tested: the test run and the acceptance criteria checked in the browser.
   - Then follow [Creating a pull request](creating-pr.md) until the pipelines pass and SonarQube reports no issue.
10. Reply with the pull request link, what was checked, the design choices the owner did not give, and the questions added.

## Related documents

- [Creating an issue](creating-issue.md)
- [Creating a pull request](creating-pr.md)
- [Testing](../conventions/testing.md)
