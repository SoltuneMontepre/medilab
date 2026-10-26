# Sonar cleanup of PR #292

## Baseline

The fresh read-only SonarCloud inventory matches pushed source `0d0cd6d0f3980663419b8fc00afff34453c1bce5`: **65 OPEN findings: 58 code smells and seven vulnerabilities; zero bugs**. Security D, maintainability A and Quality Gate ERROR; new coverage 85.7% and duplication 0.1% pass. [Complete baseline issue keys, severities, source ranges and resolved history](evidence/171-203-230-206/sonar-cleanup/baseline.json).

All 58 smell keys were already present in the earlier complete `2709021` inventory. Its former `AaF0aaGPIES1tmkRONqR` is now CLOSED/FIXED and is outside this 65-finding baseline. The seven current security keys match the owner dossier. No administrative status transition is performed.

## Issue matrix

Original locations belong to the baseline analysis. [Matching source analysis](evidence/171-203-230-206/sonar-cleanup/analysis-800652b.json) verifies every final status: **43 original findings CLOSED/FIXED; 15 intentional smells and seven security findings remain OPEN; no new issue keys**. Current lines for retained findings come from the new analysis.

| Sonar Issue Key | Rule | File | Original Status | Action | Tests | Final Status |
| --- | --- | --- | --- | --- | --- | --- |
| `AaF0FHqevCiqu-XFDLCu` | `python:S5713` | `infra/cluster/onlyoffice-monitor/probe.py:26` | OPEN | Retain covering base exception without redundant subclasses | Monitor tests and native malformed callback/updater HTTP refusals | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqevCiqu-XFDLCv` | `python:S5713` | `infra/cluster/onlyoffice-monitor/probe.py:34` | OPEN | Retain covering base exception without redundant subclasses | Monitor tests and native malformed callback/updater HTTP refusals | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqTvCiqu-XFDLCf` | `javascript:S7772` | `infra/cluster/onlyoffice/callback-signing.cjs:3` | OPEN | Explicit node: built-in imports | Node syntax, signer contracts, native pkg workers and retention | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqavCiqu-XFDLCo` | `shelldre:S7688` | `infra/cluster/onlyoffice/healthcheck.sh:10` | OPEN | Bash-native [[ tests; retain service-account sudo test commands | bash -n, real TLS readiness/drift/shutdown/restart/recreation | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqZvCiqu-XFDLCn` | `python:S7494` | `infra/cluster/onlyoffice/inspect_config.py:69` | OPEN | Direct environment comprehension preserving first equals separator | Inspector fixture tests and actual supervised worker attestation | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqXvCiqu-XFDLCm` | `shelldre:S7688` | `infra/cluster/onlyoffice/shutdown.sh:6` | OPEN | Bash-native [[ tests; retain service-account sudo test commands | bash -n, real TLS readiness/drift/shutdown/restart/recreation | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqbvCiqu-XFDLCp` | `shelldre:S7688` | `infra/cluster/onlyoffice/start.sh:15` | OPEN | Bash-native [[ tests; retain service-account sudo test commands | bash -n, real TLS readiness/drift/shutdown/restart/recreation | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqbvCiqu-XFDLCq` | `shelldre:S7688` | `infra/cluster/onlyoffice/start.sh:16` | OPEN | Bash-native [[ tests; retain service-account sudo test commands | bash -n, real TLS readiness/drift/shutdown/restart/recreation | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqbvCiqu-XFDLCr` | `shelldre:S7688` | `infra/cluster/onlyoffice/start.sh:17` | OPEN | Bash-native [[ tests; retain service-account sudo test commands | bash -n, real TLS readiness/drift/shutdown/restart/recreation | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqbvCiqu-XFDLCs` | `shelldre:S7688` | `infra/cluster/onlyoffice/start.sh:35` | OPEN | Bash-native [[ tests; retain service-account sudo test commands | bash -n, real TLS readiness/drift/shutdown/restart/recreation | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqbvCiqu-XFDLCt` | `shelldre:S7688` | `infra/cluster/onlyoffice/start.sh:38` | OPEN | Bash-native [[ tests; retain service-account sudo test commands | bash -n, real TLS readiness/drift/shutdown/restart/recreation | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqWvCiqu-XFDLCi` | `javascript:S7772` | `infra/cluster/onlyoffice/worker-bootstrap.cjs:4` | OPEN | Explicit node: built-in imports | Node syntax, signer contracts, native pkg workers and retention | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqWvCiqu-XFDLCj` | `javascript:S7772` | `infra/cluster/onlyoffice/worker-bootstrap.cjs:5` | OPEN | Explicit node: built-in imports | Node syntax, signer contracts, native pkg workers and retention | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqWvCiqu-XFDLCk` | `javascript:S7772` | `infra/cluster/onlyoffice/worker-bootstrap.cjs:6` | OPEN | Explicit node: built-in imports | Node syntax, signer contracts, native pkg workers and retention | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqWvCiqu-XFDLCl` | `javascript:S7772` | `infra/cluster/onlyoffice/worker-bootstrap.cjs:7` | OPEN | Explicit node: built-in imports | Node syntax, signer contracts, native pkg workers and retention | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqUvCiqu-XFDLCg` | `shelldre:S7688` | `infra/cluster/onlyoffice/worker.sh:4` | OPEN | Bash-native [[ tests; retain service-account sudo test commands | bash -n, real TLS readiness/drift/shutdown/restart/recreation | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqUvCiqu-XFDLCh` | `shelldre:S7688` | `infra/cluster/onlyoffice/worker.sh:5` | OPEN | Bash-native [[ tests; retain service-account sudo test commands | bash -n, real TLS readiness/drift/shutdown/restart/recreation | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHhPvCiqu-XFDLCI` | `python:S3516` | `src/core/modules/sol_laboratory/services/editing_callback_logging.py:51` | OPEN | INTENTIONAL / OWNER REVIEW — mutating logging.Filter must return True to emit sanitized and unrelated records | Native callback/editor logging and audit/redaction contracts | OPEN — OWNER REVIEW; current line 51 |
| `AaF0FHcEvCiqu-XFDLCB` | `python:S5713` | `src/core/modules/sol_laboratory/services/laboratory_editing_callback.py:59` | OPEN | Retain covering base exception without redundant subclasses | Monitor tests and native malformed callback/updater HTTP refusals | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHcEvCiqu-XFDLCC` | `python:S3358` | `src/core/modules/sol_laboratory/services/laboratory_editing_callback.py:108` | OPEN | Explicit outcome branches/status lookup with unchanged response mapping | Native callback/editor status and transaction tests | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHhTvCiqu-XFDLCN` | `python:S6353` | `src/core/modules/sol_laboratory/services/laboratory_editor_logging.py:12` | OPEN | INTENTIONAL / OWNER REVIEW — ASCII identifiers/hosts must not admit Unicode decimal digits | Origin validation, editor access and logging regressions | OPEN — OWNER REVIEW; current line 12 |
| `AaF0FHhTvCiqu-XFDLCO` | `python:S3516` | `src/core/modules/sol_laboratory/services/laboratory_editor_logging.py:28` | OPEN | INTENTIONAL / OWNER REVIEW — mutating logging.Filter must return True to emit sanitized and unrelated records | Native callback/editor logging and audit/redaction contracts | OPEN — OWNER REVIEW; current line 28 |
| `AaF0FHhNvCiqu-XFDLCE` | `python:S6353` | `src/core/modules/sol_laboratory/services/laboratory_editor_page.py:29` | OPEN | INTENTIONAL / OWNER REVIEW — ASCII identifiers/hosts must not admit Unicode decimal digits | Origin validation, editor access and logging regressions | OPEN — OWNER REVIEW; current line 29 |
| `AaF0FHhNvCiqu-XFDLCF` | `python:S3776` | `src/core/modules/sol_laboratory/services/laboratory_editor_page.py:33` | OPEN | Extract cohesive validation, orchestration and evidence responsibilities | 12 harness safety tests; full native, CRD, real save/page/desktop cohorts | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHhNvCiqu-XFDLCD` | `python:S1192` | `src/core/modules/sol_laboratory/services/laboratory_editor_page.py:36` | OPEN | Named constant with unchanged error string | Native origin/updater request and response contracts | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHhNvCiqu-XFDLCG` | `python:S6353` | `src/core/modules/sol_laboratory/services/laboratory_editor_page.py:57` | OPEN | INTENTIONAL / OWNER REVIEW — ASCII identifiers/hosts must not admit Unicode decimal digits | Origin validation, editor access and logging regressions | OPEN — OWNER REVIEW; current line 43 |
| `AaF0FHhNvCiqu-XFDLCH` | `python:S3358` | `src/core/modules/sol_laboratory/services/laboratory_editor_page.py:142` | OPEN | Explicit outcome branches/status lookup with unchanged response mapping | Native callback/editor status and transaction tests | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHhSvCiqu-XFDLCL` | `python:S3776` | `src/core/modules/sol_laboratory/services/sync_releases.py:63` | OPEN | Extract cohesive validation, orchestration and evidence responsibilities | 12 harness safety tests; full native, CRD, real save/page/desktop cohorts | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHhSvCiqu-XFDLCM` | `python:S5713` | `src/core/modules/sol_laboratory/services/sync_releases.py:91` | OPEN | Retain covering base exception without redundant subclasses | Monitor tests and native malformed callback/updater HTTP refusals | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHhQvCiqu-XFDLCJ` | `python:S1192` | `src/core/modules/sol_laboratory/services/sync_update_http.py:23` | OPEN | Named constant with unchanged error string | Native origin/updater request and response contracts | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHhQvCiqu-XFDLCK` | `python:S5713` | `src/core/modules/sol_laboratory/services/sync_update_http.py:67` | OPEN | Retain covering base exception without redundant subclasses | Monitor tests and native malformed callback/updater HTTP refusals | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHhVvCiqu-XFDLCP` | `css:S9423` | `src/core/modules/sol_laboratory/static/src/laboratory_files/editor/editor.css:11` | OPEN | Scoped editor hidden selectors outrank flex/link rules without !important | EN/VI narrow/wide Cypress visibility checks and real editor pages | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHhWvCiqu-XFDLCQ` | `javascript:S6582` | `src/core/modules/sol_laboratory/static/src/laboratory_files/editor/editor.js:5` | OPEN | Equivalent optional chaining on the DOM lookup | Cypress initialization, timeout/error and dirty-state cases | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHhWvCiqu-XFDLCR` | `javascript:S1874` | `src/core/modules/sol_laboratory/static/src/laboratory_files/editor/editor.js:28` | OPEN | INTENTIONAL / OWNER REVIEW — retain legacy beforeunload warning alongside preventDefault | Dirty/clean/handoff Cypress event regression; MDN compatibility contract | OPEN — OWNER REVIEW; current line 28 |
| `AaF0FHrNvCiqu-XFDLDh` | `javascript:S7772` | `tools/infrastructure/onlyoffice/retention_probe.cjs:3` | OPEN | Explicit node: built-in imports | Node syntax, signer contracts, native pkg workers and retention | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHrNvCiqu-XFDLDi` | `javascript:S7772` | `tools/infrastructure/onlyoffice/retention_probe.cjs:4` | OPEN | Explicit node: built-in imports | Node syntax, signer contracts, native pkg workers and retention | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHrNvCiqu-XFDLDj` | `javascript:S7772` | `tools/infrastructure/onlyoffice/retention_probe.cjs:5` | OPEN | Explicit node: built-in imports | Node syntax, signer contracts, native pkg workers and retention | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHrNvCiqu-XFDLDk` | `javascript:S9382` | `tools/infrastructure/onlyoffice/retention_probe.cjs:62` | OPEN | INTENTIONAL / OWNER REVIEW — Serial task creation/readback under process-global Date override before native GC | Native retention, signer contracts, 27-editor history and real page lifecycle | OPEN — OWNER REVIEW; current line 62 |
| `AaF0FHrNvCiqu-XFDLDl` | `javascript:S9382` | `tools/infrastructure/onlyoffice/retention_probe.cjs:63` | OPEN | INTENTIONAL / OWNER REVIEW — Serial task creation/readback under process-global Date override before native GC | Native retention, signer contracts, 27-editor history and real page lifecycle | OPEN — OWNER REVIEW; current line 63 |
| `AaF0FHrNvCiqu-XFDLDm` | `javascript:S9382` | `tools/infrastructure/onlyoffice/retention_probe.cjs:67` | OPEN | INTENTIONAL / OWNER REVIEW — Serial task creation/readback under process-global Date override before native GC | Native retention, signer contracts, 27-editor history and real page lifecycle | OPEN — OWNER REVIEW; current line 67 |
| `AaF0FHrNvCiqu-XFDLDn` | `javascript:S9382` | `tools/infrastructure/onlyoffice/retention_probe.cjs:70` | OPEN | INTENTIONAL / OWNER REVIEW — Serial task creation/readback under process-global Date override before native GC | Native retention, signer contracts, 27-editor history and real page lifecycle | OPEN — OWNER REVIEW; current line 70 |
| `AaF0FHq8vCiqu-XFDLDI` | `javascript:S7784` | `tools/infrastructure/onlyoffice/test_callback_signing.cjs:47` | OPEN | structuredClone for plain JSON signing fixtures | Seven signing-module regressions and real callback saves | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHq8vCiqu-XFDLDJ` | `javascript:S7784` | `tools/infrastructure/onlyoffice/test_callback_signing.cjs:63` | OPEN | structuredClone for plain JSON signing fixtures | Seven signing-module regressions and real callback saves | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHq8vCiqu-XFDLDL` | `javascript:S7723` | `tools/infrastructure/onlyoffice/test_callback_signing.cjs:140` | OPEN | Explicit new Array construction | Signer large-history boundary and 27-editor regression | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHq8vCiqu-XFDLDM` | `javascript:S9382` | `tools/infrastructure/onlyoffice/test_callback_signing.cjs:170` | OPEN | INTENTIONAL / OWNER REVIEW — Ordered invocations share the pinned sender fixture and check counters | Native retention, signer contracts, 27-editor history and real page lifecycle | OPEN — OWNER REVIEW; current line 170 |
| `AaF0FHrRvCiqu-XFDLDq` | `python:S3776` | `tools/infrastructure/onlyoffice/validate_crds.py:14` | OPEN | Extract cohesive validation, orchestration and evidence responsibilities | 12 harness safety tests; full native, CRD, real save/page/desktop cohorts | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqsvCiqu-XFDLC7` | `javascript:S9382` | `tools/onlyoffice_integration/browser.cjs:64` | OPEN | INTENTIONAL / OWNER REVIEW — Open/destroy/close each editor in order while the keeper maintains the same document session | Native retention, signer contracts, 27-editor history and real page lifecycle | OPEN — OWNER REVIEW; current line 64 |
| `AaF0FHqtvCiqu-XFDLC8` | `javascript:S9382` | `tools/onlyoffice_integration/browser.cjs:65` | OPEN | INTENTIONAL / OWNER REVIEW — Open/destroy/close each editor in order while the keeper maintains the same document session | Native retention, signer contracts, 27-editor history and real page lifecycle | OPEN — OWNER REVIEW; current line 65 |
| `AaF0FHqtvCiqu-XFDLC9` | `javascript:S9382` | `tools/onlyoffice_integration/browser.cjs:66` | OPEN | INTENTIONAL / OWNER REVIEW — Open/destroy/close each editor in order while the keeper maintains the same document session | Native retention, signer contracts, 27-editor history and real page lifecycle | OPEN — OWNER REVIEW; current line 66 |
| `AaF2G1TlIES1tmkRiAIM` | `javascript:S5332` | `tools/onlyoffice_integration/loopback_proxy.cjs:7` | OPEN | OWNER REVIEW — preserve existing per-finding security disposition | Proxy transport/JWT tests, real-service fixture proof; security dossier | OPEN — OWNER REVIEW; current line 7 |
| `AaF2G1TlIES1tmkRiAIN` | `javascript:S5332` | `tools/onlyoffice_integration/loopback_proxy.cjs:8` | OPEN | OWNER REVIEW — preserve existing per-finding security disposition | Proxy transport/JWT tests, real-service fixture proof; security dossier | OPEN — OWNER REVIEW; current line 8 |
| `AaF2G1TlIES1tmkRiAIQ` | `javascript:S4790` | `tools/onlyoffice_integration/loopback_proxy.cjs:155` | OPEN | OWNER REVIEW — preserve existing per-finding security disposition | Proxy transport/JWT tests, real-service fixture proof; security dossier | OPEN — OWNER REVIEW; current line 155 |
| `AaF0FHq1vCiqu-XFDLDC` | `python:S5332` | `tools/onlyoffice_integration/loopback_storage_proxy.py:84` | OPEN | OWNER REVIEW — preserve existing per-finding security disposition | Proxy transport/JWT tests, real-service fixture proof; security dossier | OPEN — OWNER REVIEW; current line 84 |
| `AaF0FHqhvCiqu-XFDLCw` | `javascript:S3776` | `tools/onlyoffice_integration/page_browser.cjs:59` | OPEN | Extract cohesive validation, orchestration and evidence responsibilities | 12 harness safety tests; full native, CRD, real save/page/desktop cohorts | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqhvCiqu-XFDLCx` | `javascript:S6353` | `tools/onlyoffice_integration/page_browser.cjs:77` | OPEN | JavaScript ASCII-equivalent \d character class | ASCII/non-ASCII equivalence check and real page admission | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqhvCiqu-XFDLCz` | `javascript:S9382` | `tools/onlyoffice_integration/page_browser.cjs:118-119` | OPEN | INTENTIONAL / OWNER REVIEW — Capture frame diagnostics in stable order before browser cleanup | Native retention, signer contracts, 27-editor history and real page lifecycle | OPEN — OWNER REVIEW; current line 123 |
| `AaF0FHqzvCiqu-XFDLC_` | `python:S3776` | `tools/onlyoffice_integration/page_sync.py:15` | OPEN | Extract cohesive validation, orchestration and evidence responsibilities | 12 harness safety tests; full native, CRD, real save/page/desktop cohorts | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqwvCiqu-XFDLC-` | `python:S3776` | `tools/onlyoffice_integration/run.py:333` | OPEN | Extract cohesive validation, orchestration and evidence responsibilities | 12 harness safety tests; full native, CRD, real save/page/desktop cohorts | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqrvCiqu-XFDLC3` | `python:S5778` | `tools/onlyoffice_integration/test_contract.py:172` | OPEN | Prepare signed inputs before the one expected failing invocation | JWT contract suite and native JWT regressions | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqrvCiqu-XFDLC4` | `python:S5906` | `tools/onlyoffice_integration/test_contract.py:221` | OPEN | assertNotIn with fixed diagnostics that cannot echo capabilities | Raw, encoded and malformed redaction contracts | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqrvCiqu-XFDLC5` | `python:S5906` | `tools/onlyoffice_integration/test_contract.py:238-240` | OPEN | assertNotIn with fixed diagnostics that cannot echo capabilities | Raw, encoded and malformed redaction contracts | FIXED — CLOSED/FIXED at `800652b` |
| `AaF0FHqrvCiqu-XFDLC6` | `python:S5906` | `tools/onlyoffice_integration/test_contract.py:241` | OPEN | assertNotIn with fixed diagnostics that cannot echo capabilities | Raw, encoded and malformed redaction contracts | FIXED — CLOSED/FIXED at `800652b` |
| `AaF2G1X8IES1tmkRiAIS` | `javascript:S5332` | `tools/onlyoffice_integration/test_loopback_proxy.cjs:16` | OPEN | OWNER REVIEW — preserve existing per-finding security disposition | Proxy transport/JWT tests, real-service fixture proof; security dossier | OPEN — OWNER REVIEW; current line 16 |
| `AaF2G1X8IES1tmkRiAIT` | `javascript:S5332` | `tools/onlyoffice_integration/test_loopback_proxy.cjs:18` | OPEN | OWNER REVIEW — preserve existing per-finding security disposition | Proxy transport/JWT tests, real-service fixture proof; security dossier | OPEN — OWNER REVIEW; current line 18 |
| `AaF2G1X8IES1tmkRiAIV` | `javascript:S5332` | `tools/onlyoffice_integration/test_loopback_proxy.cjs:76` | OPEN | OWNER REVIEW — preserve existing per-finding security disposition | Proxy transport/JWT tests, real-service fixture proof; security dossier | OPEN — OWNER REVIEW; current line 76 |

## Sonar before and after

| Metric | Baseline `0d0cd6d` | Verified source `800652b` |
| --- | --- | --- |
| OPEN code smells | 58 | 15 |
| OPEN vulnerabilities | 7 | 7 |
| Bugs | 0 | 0 |
| Security Rating | D | D |
| Maintainability / Reliability | A / A | A / A |
| Quality Gate | ERROR | ERROR — security-owner gate only |
| New coverage | 85.7% | 85.8% |
| New duplication | 0.1% | 0.1% |
| Newly introduced findings | — | 0 |

All six original cognitive-complexity issues are CLOSED/FIXED, including the complexity-36 runner. No safe style/complexity correction from the original inventory is deferred. The remaining 15 code-smell findings preserve intentional ordering, logging emission, ASCII validation and browser compatibility; their statuses are not administratively changed.

## Hosted source checkpoint

All results below are for `800652b`; [final containing-document SHA and latest checks](https://github.com/SoltuneMontepre/medilab/pull/292#issuecomment-6422726597) are recorded separately.

| Workflow / check | Result |
| --- | --- |
| [ci-core](https://github.com/SoltuneMontepre/medilab/actions/runs/40362588543) | FAIL — only Sonar security-owner gate; all implementation jobs PASS |
| [ci-infra](https://github.com/SoltuneMontepre/medilab/actions/runs/40362588501) | PASS |
| [ci-mobile-app](https://github.com/SoltuneMontepre/medilab/actions/runs/40362588359) | PASS; native compilation filter-SKIPPED |
| [ci-sync-app](https://github.com/SoltuneMontepre/medilab/actions/runs/40362588275) | PASS |
| [ci-tools](https://github.com/SoltuneMontepre/medilab/actions/runs/40362588489) | PASS |
| GitGuardian | FAIL — incident 39039733 pending authorized false-positive review |
| SonarCloud Code Analysis | FAIL — same seven OPEN security findings |
| Branch and PR naming | PASS |

CodeRabbit remains skipped for Draft PRs; its success context is not an approving review. No independently fixable implementation failure remains.

## Behavior-sensitive decisions

The nine sequential-await findings retain ordering: retention changes a process-global clock and reads back each write; the signer test shares counters; the large-history browser churn keeps a keeper alive and tears down each participant before the next; page diagnostics finish before browser cleanup. Parallel execution would change the exercised lifecycle.

Both logging filters mutate every sensitive representation and return True so sanitized records still reach handlers. Returning False drops required diagnostics. [Python 3.12 logging.Filter contract](https://docs.python.org/3.12/library/logging.html#logging.Filter.filter). The three Python numeric patterns remain ASCII-only; Python \d also matches Unicode decimal digits. The JavaScript numeric pattern uses equivalent ASCII \d semantics.

The editor retains preventDefault plus the legacy returnValue assignment. [Browser compatibility contract](https://developer.mozilla.org/en-US/docs/Web/API/Window/beforeunload_event). Cypress checks dirty, clean and handoff events as well as hidden messages/retry controls at narrow/wide sizes in English and Vietnamese. The selector change is scoped to the editor root and its descendants.

## Verification and delivery

Source checkpoint: `800652b1a614254967772429605645f9ec0b01f9`. The [source manifest](evidence/171-203-230-206/sonar-cleanup/source-manifest.json) identifies the same mounted source contents tested before committing. Final pushed SHA and completed checks: [verified delivery status](https://github.com/SoltuneMontepre/medilab/pull/292#issuecomment-6422726597). The final containing documentation commit and latest hosted SHA are recorded there; this report does not attribute older analyses to a later commit.

| Commit | Verified scope |
| --- | --- |
| `e9cdac7` | Bash-native tests, explicit Node built-ins and plain-JSON fixture cloning. |
| `52c8a85` | Covering exception classes, environment construction, stable error constants and precise redaction assertions. |
| `af8a62b` | Separate native evidence classification from engine orchestration; twelve lifecycle/reporting regressions. |
| `5218bb2` | Extract cohesive origin, catalog, CRD, page input and desktop observation responsibilities. |
| `800652b` | Editor selector specificity, equivalent optional chaining and unload/visibility regression coverage. |

[Sanitized local results](evidence/171-203-230-206/sonar-cleanup/local-results.json) distinguish passing repeats from retained fixture failures. Full Laboratory/Commerce/Inventory: **1,846 tests, zero failures/errors**; targeted callback/JWT/logging/editor/updater: **87 passed**. Six actual callback cases cover DOCX/XLSX/PPTX, duplicate idempotency, 27-editor history and fresh-JWT redelivery, including a 370-second expiry case. Four actual released-page/coediting cases and one actual Rust desktop observation pass. All nine additional real-service cases also pass, including the 650-second callback, real bucket-failure recovery, captured-delivery authentication controls, concurrent-version preservation, untrusted TLS refusal, finite retry exhaustion, history compatibility and two authorized editors. Together the two nonoverlapping cohorts execute all 15 real-service cases.

Cypress: **eight passed, zero pending/skipped**, including EN/VI at 390/1440 pixels and dirty/clean/handoff warnings. Runtime contracts: 39 infrastructure Python, 60 integration Python, seven proxy Node and seven signing Node cases pass. Rust: **213 passed / 18 ignored** by default; the separately selected live updater signature/data-preservation case and live desktop observer each pass. Bun: **53 passed**; Mobile: **four passed**. Strict Clippy, Rust formatting, frontend production build, OpenAPI, nine Taskfile checks and typechecking pass; typechecking reports zero errors and 6,364 warnings in 713 files.

The real TLS wrapper passes readiness and native worker drift refusal. Graceful stops exit zero without OOM; restart and recreation preserve synthetic volume markers. Native GC retains a two-day object and removes an eight-day object under the unchanged 604800-second policy; this is not seven elapsed days. Pinned manifests validate 14 resources and 18 custom resources; kubeconform's 16 custom-resource skips remain separately stated. The final live fixture inventory verifies strict internal isolation, project-owned peers, one network per peer and no published ports. A different peer cannot reach the Document Server's loopback storage listener.

Full `task lint` retains exactly E8102 at Commerce `portal.py:64` and W8163 at `product_template.py:108,109`. No related business behavior or rule changes. Initial missing-bucket, absent-loopback-adapter and updater network-variable failures are retained with corrected passing repeats; a zero-test setup failure is never acceptance. Raw logs, JWTs, capabilities, environment values and signing material are absent from shared evidence.

The seven security findings retain four proposed False Positives and three proposed scoped ACCEPT decisions. GitGuardian incident 39039733 retains its separate commit-ID false-positive investigation and pending authorized review. No exclusions, rules, thresholds, credentials, signing keys or isolation controls change. The three Commerce lint decisions remain unchanged. PR #292 remains Draft; no merge or deployment is authorized.

## Related documents

- [Integration acceptance](171-203-230-206-acceptance.md)
- [Sonar owner dossier](../security/pr-292-sonar-disposition-review.md)
- [GitGuardian review](../security/pr-292-gitguardian-review.md)
- [Real callback receipts: six cases](evidence/171-203-230-206/sonar-cleanup/real-callbacks.json) and [nine additional cases](evidence/171-203-230-206/sonar-cleanup/real-callbacks-additional.json)
- [Real page receipts](evidence/171-203-230-206/sonar-cleanup/real-pages.json) and [desktop observer](evidence/171-203-230-206/sonar-cleanup/desktop-observer.json)
- [TLS lifecycle](evidence/171-203-230-206/sonar-cleanup/tls-lifecycle.json), [native retention](evidence/171-203-230-206/sonar-cleanup/retention.json) and [owned cleanup](evidence/171-203-230-206/sonar-cleanup/cleanup.json)
- [Harness and fixture ownership](../../tools/onlyoffice_integration/README.md)
