# Reviewing a pull request

How a pull request is checked against the conventions, the business rules and the database, and how the review is written.

## Steps

1. **Read the conventions** before anything else: [AGENTS.md](../../AGENTS.md), the [docs index](../readme.md) and the [conventions](../conventions/readme.md), then the ones the change touches, such as [Database](../conventions/database.md) and [Python](../conventions/python.md).
2. **Read the change:** `gh pr view <pr> --json title,headRefName,files` and the diff.
3. **Check it out in the main repository**, because the local Odoo mounts it: `gh pr checkout <pr>`. When local changes would be overwritten, stash only the files that conflict and say so.
4. **Read the business rules** the change touches: [Business rules](../business/readme.md), the feature documents of the module and the [specs](../specs/readme.md). A rule the documents state outranks the code.
5. **Read the pipeline results:** `gh pr checks <pr>`. The pipelines run the tests and SonarQube; do not run the test suite again.
6. **Check the database** when the change touches models: run `task upgrade`, then follow the steps of [Syncing the database diagram](syncing-database-diagram.md) to read the live schema. Look for missing constraints, missing indexes, delete rules that differ from the business rules, and differences from the diagram.
   - When the upgrade fails on records already in the local database, install the modules into a scratch database instead and read the schema there: create it with `docker exec medilab-postgres psql -U root -d medilab -c "create database <scratch>"`, then run `docker compose -f tools/infrastructure/docker-compose.yml run --rm -T odoo -d <scratch> -i <modules> --stop-after-init`. Leave the local database as it is, and say in the review that the schema came from a scratch database.
7. **Write the findings**, as below.
8. **Show the owner the findings** and wait for the answers to the questions, then post the review once the owner says to.

## Writing the findings

- A finding is a statement of what differs from a convention or a rule, with a link to the line. Link to the commit that was reviewed, not to a branch.
- A question the owner can answer, such as what the rule is, is asked to the owner before posting and never posted to the author. The review carries the answer as a statement.
- A finding that the documents are wrong or missing a rule says which document needs updating and what it should say. The reviewer does not edit the documents.
- Say what was checked and what was not, including the pipeline results.

## Posting

- Post one review with `gh pr review <pr> --comment --body-file <file>`. Inline comments work only on lines in the diff; the review body carries the links for the others.
- Edit a posted review with `gh api -X PUT repos/<owner>/<repo>/pulls/<pr>/reviews/<id> -F body=@<file>`. A submitted review cannot be deleted through the API.
- The review carries no attribution lines.

## Rules

- Do not commit, push or change files on the pull request's branch.
- Do not claim the database matches until the upgrade ran on the pull request's code.

## Related documents

- [Syncing the database diagram](syncing-database-diagram.md)
- [Creating a pull request](creating-pr.md)
- [Git](../conventions/git.md)
