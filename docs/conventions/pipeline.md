# Pipelines

How the GitHub Actions workflows in `.github/workflows/` are written.

## Files and names

- One workflow per area and stage: `ci.<area>.yml` checks a change, `cd.<area>.yml` deploys it.
- The workflow `name` is the file name without the extension and dots: `ci-core`, `cd-infra`.
- The concurrency group is `medilab-<name>`, with `-${{ github.ref }}` for CI. CI sets `cancel-in-progress: true`; CD sets `false`, so a deployment is never cut off.
- Every workflow can also be started by hand with `workflow_dispatch`.

## Triggers and change detection

The relevant paths of a workflow are its area's folders and the workflow file itself.

### CI: runs on every change, works only on relevant ones

Branch protection requires CI jobs, and a workflow that a `paths:` filter keeps from starting never reports them. So:

- Do not filter the trigger with `paths:`. A CI workflow starts on every pull request.
- Each job always starts. The first steps detect whether the change is relevant with `dorny/paths-filter`; every later step has `if: <relevant> || github.event_name == 'workflow_dispatch'`.
- A change that is not relevant finishes green without doing anything. A manual run always does the work.
- When several jobs share the detection, or a rule needs more than path patterns, put it in a `changes` job and have the others depend on it with `needs`. `ci-core` does this to ignore Markdown under `src/core`.

### CD: runs only on relevant changes

CD jobs are not required checks, so a CD workflow filters its trigger instead:

- Trigger on `push` to `main` with `paths:` listing the relevant paths.
- Steps have no relevance conditions; a CD run always does the work.

## Jobs

- Run on `ubuntu-24.04` and set `timeout-minutes`.
- Set the least `permissions`. `contents: read` is the workflow default; a job that needs more declares it itself, such as `pull-requests: read` on the job whose change detection reads pull request files.
- Order jobs so cheap checks fail first, and have each stage `needs` the one before it.
- A job that needs secrets fails on a fork pull request with a message saying why, instead of being skipped: a skipped required check counts as passing.
- A check with a pass or fail result elsewhere, such as the SonarQube Cloud quality gate, waits for that result and fails the job with it.
- Use `defaults.run.working-directory` for a job that works in one folder, such as `infra`.
- Name every step with a short action: "Terraform fmt check".
- Pin actions to a major version tag: `actions/checkout@v7`. SonarQube ignores its rule S7637 (full commit SHA) for `.github/`, set in `sonar-project.properties`.

## Images and artifacts

- Pass an image between jobs through the GitHub Actions build cache (`cache-to: type=gha,mode=max`, then `cache-from` with `load: true`), not through a registry or an artifact.
- Only `cd` workflows push images, tagged with the full commit SHA.
- Set `DOCKER_BUILD_RECORD_UPLOAD: false` on `docker/build-push-action`.
- Upload artifacts with `retention-days: 1`; they only pass files between jobs of one run.

## Secrets

- Credentials come from the `secrets` context. Doppler is their source; see [Secrets](../infrastructure/secrets.md).
- Secrets are created via Terraform in Github Actions. If an action needs a secret, add it to the workflow's `env:` and use it from there. Do not read secrets from files or defaults.

## Related documents

- [Pipelines](../infrastructure/pipelines.md)
- [Git](git.md)
- [Creating a pull request](../workflows/creating-pr.md)
- [Taskfiles](taskfiles.md)
- [Secrets](../infrastructure/secrets.md)
