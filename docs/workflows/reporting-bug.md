# Reporting a bug

How a defect becomes a GitHub bug issue.

A bug is behaviour that differs from what the documents say. Behaviour the documents do not describe is not a bug: it is a gap in the documents, added to `questions/<topic>.md` or proposed as a feature instead.

## Steps

1. **Collect the report.** What happened, the steps that lead to it, what was expected, screenshots or logs, and where it happened (local, staging or production; which module and screen).
2. **Find the expected behaviour** in the documents: the rule or acceptance criterion the behaviour breaks, and the user stories it belongs to. If no document says what should happen, stop and report the gap instead.
3. **Check for duplicates:** `gh issue list --state all --search "<keywords>"`. If an issue already reports it, add the new details there instead.
4. **Reproduce it** on the local app when possible (`task up`), and note whether it reproduced.
5. **Draft the issue** from [the bug template](../../.github/ISSUE_TEMPLATE/bug-ticket.md):
   - Title: `[Defect | <scope>] <short description>`, where the scope is the module, such as `Laboratory`.
   - The template's sections, with the expected behaviour linked to the document rule it comes from.
   - **Affected stories:** the user story IDs the bug breaks.
6. **Ask who to assign**, from the people in [Creating an issue](creating-issue.md#people). The owner can choose several people or nobody.
7. **Create the issue** once the owner has seen the title and summary: `gh issue create --title "<title>" --body-file <file> --label bug --assignee <login>`. Then set the issue type to Bug.
8. Reply with the issue link, the rule it breaks and whether it reproduced.

## Related documents

- [Fixing a bug](fixing-bug.md)
- [Creating an issue](creating-issue.md)
