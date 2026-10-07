# Creating a pull request

What to do from opening a pull request until it is ready for review. A pull request is not finished when it is opened: wait for the pipelines and for SonarQube, and fix what they report.

## Steps

1. Check the branch and title against [Git](../conventions/git.md).
2. Open the pull request.
3. Wait for every pipeline to finish: `gh pr checks <pr> --watch`.
4. Fix every failed pipeline, push, and wait again.
5. Check SonarQube for the pull request, as below.
6. Fix, push, and repeat from step 3 until the pipelines pass and the quality gate is `OK`.

## Checking SonarQube

SonarQube Cloud analyses a pull request in the `ci-core` pipeline, so check it only after that pipeline has finished.

1. Find the project key: `sonar.projectKey` in `sonar-project.properties`.
2. Find the pull request key with `list_pull_requests`. Use it as `pullRequest`, never the git branch name.
3. Read the quality gate with `get_project_quality_gate_status`.
4. List the open issues with `search_sonar_issues_in_projects` for the pull request.
5. Fix each issue in the code. Where an issue cannot or should not be fixed, change its status with `change_sonar_issue_status`:
   - `falsepositive`: the rule is wrong for this code.
   - `accept`: the finding is real and the owner agreed to keep it.
   - Always add a comment that says why.

## Rules

- Do not mark an issue accepted or false positive without the owner's approval; report it instead.
- A pull request with an `ERROR` quality gate or an open issue is reported to the owner with what remains and why.
- Say in the reply what was checked: which pipelines passed and what the quality gate and issue count were.

## Related documents

- [Git](../conventions/git.md)
- [Pipelines](../conventions/pipeline.md)
