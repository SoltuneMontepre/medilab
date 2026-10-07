# Pipelines

How the GitHub Actions workflows in `.github/workflows/` are written.

## Files and names

- One workflow per area and stage: `ci.<area>.yml` checks a change, `cd.<area>.yml` deploys it.
- The workflow `name` is the file name without the extension and dots: `ci-core`, `cd-infra`.
- The concurrency group is `medilab-<name>`, with `-${{ github.ref }}` for CI. CI sets `cancel-in-progress: true`; CD sets `false`, so a deployment is never cut off.
- Every workflow can also be started by hand with `workflow_dispatch`.

## Runs on every change, works only on relevant ones

Branch protection requires these jobs, and a workflow that a `paths:` filter keeps from starting never reports them. So:

- Do not filter the trigger with `paths:`. The workflow starts on every pull request, or every push to `main`.
- Each job always starts. The first steps detect whether the change is relevant with `dorny/paths-filter`; every later step has `if: <relevant> || github.event_name == 'workflow_dispatch'`.
- A change that is not relevant finishes green without doing anything. A manual run always does the work.
- The relevant paths of a workflow are its area's folders and the workflow file itself.
- When several jobs share the detection, or a rule needs more than path patterns, put it in a `changes` job and have the others depend on it with `needs`. `ci-core` does this to ignore Markdown under `src/core`.
- A job that only applies to some pull requests uses a job-level `if`, such as the SonarQube scan skipping pull requests from forks.

## Jobs

- Run on `ubuntu-24.04` and set `timeout-minutes`.
- Set the least `permissions`. `contents: read` is the workflow default; a job that needs more declares it itself, such as `pull-requests: read` on the job whose change detection reads pull request files.
- Order jobs so cheap checks fail first. `ci-core` runs `changes`, then `lint` and `build`, then `test`, then `sonarqube`; each stage needs the one before it.
- A pull request from a fork cannot read secrets, so the `sonarqube` job fails on it with a message instead of being skipped; a skipped required check counts as passing and would let the quality gate be bypassed. Contributors push a branch to the repository instead.
- The `sonarqube` job waits for the SonarQube Cloud quality gate (`-Dsonar.qualitygate.wait=true` in the scan step) and fails when the gate fails, including on coverage.
- Use `defaults.run.working-directory` for a job that works in one folder, such as `infra`.
- Name every step with a short action: "Terraform fmt check".
- Pin actions to a major version tag: `actions/checkout@v7`. SonarQube ignores its rule S7637 (full commit SHA) for `.github/`, set in `sonar-project.properties`.

## Images

- `ci-core` pushes the image it builds to GitHub Container Registry as `ghcr.io/soltunemontepre/medilab-odoo:pr-<number>`, overwritten on each push to the pull request, and later jobs pull it instead of building again.
- `cd-core` publishes the release image `ghcr.io/soltunemontepre/medilab` when `src/core` or the Dockerfile changes on `main`, tagged with the full commit SHA and `latest`. Deploy and roll back by the SHA tag. Release images are a separate package from the pull request images, and no cleanup deletes them.
- A fork pull request cannot push, so its `build` job only builds and its `test` job rebuilds the image from the build cache.
- `cd-cleanup` runs when a pull request is closed, merged or not, and can be run by hand. It deletes the images, artifacts and build caches of every pull request that is no longer open, and untagged images left by overwritten tags. GitHub does not delete the last tagged version of a package, so when no open pull request has an image the whole `medilab-odoo` package is deleted; the next pull request build creates it again.
- Artifacts are kept for one day, and `docker/build-push-action` does not upload build records (`DOCKER_BUILD_RECORD_UPLOAD: false`).

## Secrets

- Credentials come from the `secrets` context. Doppler is their source; see [Secrets](../infrastructure/secrets.md).
- Secrets are created via Terraform in Github Actions. If an action needs a secret, add it to the workflow's `env:` and use it from there. Do not read secrets from files or defaults.

## Related documents

- [Git](git.md)
- [Creating a pull request](../workflows/creating-pr.md)
- [Taskfiles](taskfiles.md)
- [Secrets](../infrastructure/secrets.md)
