# Creating an issue

How a feature in the functional documents becomes a GitHub feature issue.

## Story status

User story IDs, such as `US-AD01`, link the documents to GitHub. Every feature issue lists the stories it covers on its **Stories** line. The status of a story comes from GitHub, never from the documents:

| GitHub                                       | Status      |
| -------------------------------------------- | ----------- |
| No issue lists the story                     | Not started |
| An open issue lists it                       | Planned     |
| That issue has an open pull request          | In progress |
| That issue was closed by a merged pull request | Done      |

Find the issues of a story with `gh issue list --state all --search "US-AD01 in:body"`, and their pull requests with `gh pr list --state all --search "<issue number>"`.

## Readiness

A story is ready for an issue when:

- its feature section has rules and acceptance criteria;
- its tables are in the [database diagrams](../infrastructure/readme.md);
- no question in `questions/<topic>.md` names it as blocked;
- its [spec](../specs/readme.md) exists, when the feature needs one.

## Steps

1. **Find the feature.** Take it from the functional documents: a feature section of an actor document, with its user stories. When the user names no feature, list the stories that are not started and ready, grouped by feature, and ask which one.
2. **Check its status and readiness** as above, and the code (the models, views and tests of its tables).
   - If an issue already covers its stories, report that issue instead of creating a new one.
   - Report what is not ready, and the issues the feature depends on, such as accounts and permissions before any feature with access rules. Stop until the owner says how to go on.
   - When the feature needs a spec that does not exist, offer to write it first.
3. **Draft the issue** from [the feature template](../../.github/ISSUE_TEMPLATE/feature-ticket.md):
   - Title: `[Feature | <scope>] <feature name>`, where the scope is the module, such as `Laboratory`.
   - **Stories:** every story ID the issue covers.
   - **Purpose:** what the feature lets someone do.
   - **Description:** what to build as a checklist: models with their tables from the diagram, views, menus, access rules. Then the rules that apply to every part, the conventions to follow and what is out of scope.
   - **Demo data:** the records the feature adds to the `sol_demo` module, following [demo data](../conventions/demo_data.md): a record in each status and the cases the acceptance criteria name.
   - **Acceptance criteria:** the feature's acceptance criteria from its document as a checklist, plus tests that cover them and a browser test of the feature's main path.
   - **References:** the spec, then the documents, diagram and existing code. Link documents on `main`; if they are only in an open pull request, say the issue is read after it is merged.
4. **Ask who to assign**, from the people below, as a lettered list the owner answers with letters, such as "A, C". F is nobody.
5. **Create the issue** once the owner has seen the title and summary: `gh issue create --title "<title>" --body-file <file> --assignee <login>`. Then set the issue type to Feature.
6. Reply with the issue link, the stories it covers, the assignees, and the dependencies found in step 2.

## People

|     | GitHub login  | Name                |
| --- | ------------- | ------------------- |
| A   | `hatohui`     | Le Sy Tuyen         |
| B   | `HuyDG160205` | Dinh Gia Huy        |
| C   | `KietPham-VN` | Pham Anh Kiet       |
| D   | `nnh53`       | Nguyen Nam Hoang    |
| E   | `hzanhle`     | Le Nguyen Hoang Anh |
| F   |               | Nobody              |

## Chores

Work that is neither a feature nor a bug, such as tooling or demo data, is a chore issue. Its title is `[Chore | <scope>] <short description>`, where the scope is the module or area, such as `Tooling`. Set the issue type to Task.

## Epics

Work that spans several features of one business area is an epic: a parent issue whose sub-issues are the feature and chore issues that build it.

- Its title is `[Epic | <scope>] <area>`. Set the issue type to Feature. An epic has no assignee; its sub-issues do.
- Its body states the goal, links the documents and spec of the area, and gives the order of its sub-issues.
- Each sub-issue is a feature or chore issue as above, small enough for one pull request, and is added to the epic as a GitHub sub-issue.
- A sub-issue that needs another one first records it with GitHub's **blocked by** relationship and names it in its body.
- A sub-issue that changes existing code says what is already on `main` in a **Starting point on main** line of its Description.
- A sub-issue may be created before its new tables are in the database diagrams when the documents describe them; its first step adds those tables to the diagram. This is the only exception to [Readiness](#readiness).

## Related documents

- [Resolving an issue](resolving-issue.md)
- [Specs](../specs/readme.md)
- [Documentation conventions](../conventions/documentation.md)
- [Git](../conventions/git.md)
