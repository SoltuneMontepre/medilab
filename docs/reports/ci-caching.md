# Reducing CI time and reusing test results

MediLab’s browser-test step took 27–28 minutes in two successful pull request runs. For a retry of the same run, GitHub can already preserve successful jobs. For new commits, the first experiment worth measuring is a faster browser-test job. Use `act` to test workflow changes locally. Its caches speed up local setup, and GitHub still evaluates the required check for the commit under review. [GitHub reruns](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs) · [act project](https://github.com/nektos/act) · [Required status checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks)

## Where the time went

GitHub run and step timestamps give the elapsed times below. The three indented E2E steps are part of the E2E job. The type check and Odoo test shards run alongside it. [Core CI workflow](../../.github/workflows/ci.core.yml)

| Elapsed time (minutes:seconds) | [PR run 44314048947](https://github.com/SoltuneMontepre/medilab/actions/runs/44314048947) | [PR run 44335153977](https://github.com/SoltuneMontepre/medilab/actions/runs/44335153977) |
| --- | ---: | ---: |
| Entire `ci-core` run | 35:50 | 38:31 |
| E2E job | 32:30 | 34:29 |
| ↳ Build image from cache | 0:59 | 1:28 |
| ↳ Start Odoo with demo data | 3:59 | 4:02 |
| ↳ Browser tests | 27:15 | 28:20 |
| Type check in the lint job | 9:55 | 9:10 |

The browser step installs Bun dependencies and the Cypress binary, runs the Node helper tests and launches Cypress. In the second run, Cypress reported 26:33 across 76 specs within the 28:20 browser step. [E2E job log](https://github.com/SoltuneMontepre/medilab/actions/runs/44335153977/job/134910757358) · [Test entry point](../../src/tests/package.json)

A successful `cd-core` run took **6:35**, including **0:54** to build and push and **4:12** waiting for the release. That wait checks the live deployment. Keep it on each release. [CD run 44329511770](https://github.com/SoltuneMontepre/medilab/actions/runs/44329511770) · [Core CD workflow](../../.github/workflows/cd.core.yml)

A third PR illustrates when a retry can save most of the wait. Its E2E job passed in **34:40** and its SonarQube job failed. If the cause can clear on the same revision and the coverage artifacts are still available, a failed-jobs rerun would retry SonarQube and preserve the E2E result. [PR run 44323878037](https://github.com/SoltuneMontepre/medilab/actions/runs/44323878037) · [GitHub reruns](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)

## What can be reused today

- **Retry a failed hosted run.** Run `gh run rerun RUN_ID --failed` on the original run. GitHub reruns failed jobs and their dependents on the same SHA and ref. Other jobs keep their previous outputs. If the single E2E job failed, its entire test command runs again. MediLab retains coverage artifacts for one day, so check availability on a delayed retry that needs them. [GitHub reruns](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs) · [Core CI workflow](../../.github/workflows/ci.core.yml)
- **Reuse downloads and build layers.** GitHub’s cache restores files by key. BuildKit imports and exports image layers. MediLab already exports its core image build cache with `type=gha,mode=max` and imports it in the test jobs. A cache hit says files were available. The job still needs to establish its result. A cache written on a PR’s merge ref is scoped to that PR. [Dependency caching](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching) · [BuildKit cache](https://docs.docker.com/build/cache/backends/gha/) · [Core CI workflow](../../.github/workflows/ci.core.yml)
- **Get local feedback with `act`.** From the repository root, `act pull_request -W .github/workflows/ci.core.yml --list` lists the PR jobs. Use `-j` to select a job for execution. The local cache service stores workflow cache files under `--cache-server-path`. Downloaded action code uses `--action-cache-path`. The `--reuse` flag preserves containers across runs. These stores are local by default. A local pass does not publish a GitHub check. Runner images differ from hosted VMs, and `act` documents gaps in event context, job permissions and deployment environments. [act guide](https://nektosact.com/) · [Usage](https://nektosact.com/usage/) · [CLI flags](https://github.com/nektos/act/blob/main/cmd/root.go) · [Runner images](https://nektosact.com/usage/runners.html) · [Compatibility](https://nektosact.com/not_supported.html)

On the MediLab checkout, `act` v0.2.98 listed all nine `ci-core` job IDs for `pull_request`, including `e2e`, `test-runner` and the final `sonarqube` job. This check exercised workflow discovery. It did not execute jobs or measure a warm local cache. [Verified act release](https://github.com/nektos/act/releases/tag/v0.2.98)

## MediLab trials

1. **Measure and cache E2E setup.** The CI trial records dependency installation, Cypress installation, Node tests and browser timings. It caches `~/.bun/install/cache` and `~/.cache/Cypress` by OS, architecture, Bun version and test lockfile. The single-runner job reached spec 62 of 76 when its 45-minute budget expired. [Single-runner attempt](https://github.com/SoltuneMontepre/medilab/actions/runs/44348630068) · [Core CI workflow](../../.github/workflows/ci.core.yml)
2. **Split the browser suite.** In the baseline, 17 specs covering WF-02 through WF-07 took 13:48 and the other 59 took 14:12, measured from spec start to report. The matrix gives each group its own Odoo demo. In the first matrix run the remaining group passed, the laboratory-flows browser step failed, and the required test check reported failure. This leaves the warm-cache speedup unverified. [Matrix attempt](https://github.com/SoltuneMontepre/medilab/actions/runs/44357714640) · [CI pull request](https://github.com/SoltuneMontepre/medilab/pull/634)
3. **Measure possible result reuse across commits.** A documentation-only follow-up on a PR that already changed core can still trigger the full suite because the path filter sees the cumulative PR diff against the base. First log potential matches while executing every test. Start with a deterministic check and fingerprint its complete inputs in the tested merge tree, including tests, helpers, workflows, resolved actions, toolchain, image digests and relevant environment. For any later reuse, require a trusted hosted run that actually executed and passed that check, link the source job, and report the decision on the current PR SHA. Run the check in full on a changed base, missing inputs or uncertain provenance, and on manual runs. Keep Sonar’s live gate and CD outside this experiment. A partial cache key or an earlier green PR cannot establish that the current inputs passed. [PR path filtering](https://github.com/dorny/paths-filter#supported-workflows) · [Required checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks) · [Action inputs and outputs](https://bazel.build/remote/caching#overview) · [Pipeline conventions](../conventions/pipeline.md)

## How large teams select E2E tests

GitLab selects merge-request E2E tests from changed files, labels and code-path mappings. Its pipeline can run the full suite on demand and uses test durations to distribute work. Slack described keeping a small set of critical Webapp flows before merge, checking a wider set before deployment and batching the remaining regression tests. Google recommends checking whether a focused integration test can detect the same defect before adding another end-to-end test. [GitLab E2E testing](https://docs.gitlab.com/development/testing_guide/end_to_end/) · [Slack CI design](https://slack.engineering/balancing-safety-and-velocity-in-ci-cd-at-slack/) · [Google Testing Blog](https://testing.googleblog.com/2015/04/just-say-no-to-more-end-to-end-tests.html)

For MediLab, trial a critical smoke set plus affected flows on each PR. Compare the selection with uncached full-suite runs before enabling it as a merge gate. Track time to PR feedback and regressions found only by the full suite. [Result-cache options](ci-s3-cache.md)

## Related documents

- [MediLab pipelines](../infrastructure/pipelines.md)
- [Testing conventions](../conventions/testing.md#running-browser-tests)
