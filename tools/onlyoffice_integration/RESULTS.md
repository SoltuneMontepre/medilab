# Independent callback verification results

Executed on 2026-10-25 UTC using isolated local resources. The double-encoded URL redaction defect is fixed by the supplied callback commit. Real Office saves and the original ten opt-in cases passed. Combined release acceptance remains blocked by a real large-history JWT incompatibility and an infrastructure settings propagation gap.

## Exact sources and runtime

| Component | Tested identity |
| --- | --- |
| Reviewed callback base | `fa8031db9eee3108211d771e09a57f20c038e4ad` |
| Official callback security fix | `a3cec45f17f2429f99ae8556391c5750e38cc80a` |
| Original integration harness | `27fa44c8436206765dd5bfa9f12099761af3f712`, preserved; cherry-picked as `4b4bbff362f6534c032e92d9f4bb82037fb87c5e` on the separate a3 branch |
| Main 13-case real run | Harness `3dbc65e5735ac21b45690a56d8791e9dd4f8f752`; clean source diff |
| Isolated expiry run | Harness `16f10909985a00af44fdb7f7326e3165c86c4275`; clean source diff |
| Explicit outcome verification | Harness `2a1e59b0e218f89613f9dccfbf2799547ebaff56` |
| Infrastructure handoff inspected | `5b42e14f5715f21f85f525911cd8f692ae51302e`, including its committed Agent 4 runtime handoff and settings |
| Document Server image index | `docker.io/onlyoffice/documentserver:9.4.0.1@sha256:3ab6ebc7c605e5a32b7ae3ff19daed4925090245acc8100ce2230bd766c88212` |
| amd64 manifest | `sha256:e231bc62da8c1f0c1f78188f8c7e17e67716f38955d0ad1d703cf911ad6db84b` |
| Image configuration ID | `9f1f9ada40561752ba2597da8fe6e51fe7e09ba2b76cebdb4377ce004d88e5a3` |
| Installed package / command API | `9.4.0-129` / `9.4.0.129` |
| DocService executable SHA-256 | `556df4aab7b1a87123046a4459baee34e60f57deaf7bcd189bccd6f271bd8fcb` |
| Converter executable SHA-256 | `ac76144203fd4e8fdee4cccac976697e87ec9b67b7bdf572e6ea1288524a8f80` |
| Odoo image | `medilab-odoo:issue-171-callback`, ID `d1e0a91af55b9176fdcf60125a1f3aa40a99e3e83ac779a857eae0b0afa06a19`; Odoo `20.0-20260926`, PyJWT `2.15.1` |
| Garage | `2.4.1`, digest `sha256:9c96caa2612d3411acc5b0e6701fb238dbfba33e533a6d7d3d811a4b12d0d020` |
| PostgreSQL / browser | PostgreSQL `18.6`; Playwright `1.56.1` with Chromium |
| Host | Linux `7.3.0-4-cachyos`, amd64; rootless Podman `6.1.4`, Compose `5.6.1` |

The verification worktree is `/home/leon/Projects/medilab-wt-171-security-verification`, branch `test/171-onlyoffice-security-verification`. It descends from a3; the original callback worktree, original test branch/history, infrastructure branch and #230 branch were not rewritten. All new commits use author and committer KietPham-VN with the requested noreply email.

The current host permits local sockets, rootless Podman and isolated container networking. The root Docker/Podman socket remains inaccessible. Commands use only `/run/user/1000/podman/podman.sock`; no permission or security-control changes were made. Projects `medilab171-agent4`, `medilab171-agent4-security` and `medilab171-agent4-stress` own all resources. There are no published host ports or production connections. PostgreSQL and Garage are Odoo fixtures, not dependencies inside Document Server.

## Executed counts

Repeated cohorts are listed separately and must not be added as independent test coverage.

| Suite/cohort | Passing | Failing | Skipped | Blocked |
| --- | ---: | ---: | ---: | ---: |
| Pure production JWT/origin/logging contract suite on a3 | 24 | 0 | 0 | 0 |
| Native Odoo HTTP/logging suite on a3 (27 HTTP + 11 logging) | 38 | 0 | 0 | 0 |
| Original ten real-service cases, across completed a3 cohorts | 10 | 0 | 0 | 0 |
| All fourteen distinct native cases, across completed a3 cohorts | 13 | 1 | 0 | 0 |
| Fresh native-entrypoint comparison, 13 selected cases | 12 | 1 | 0 | 0 |
| Fixed expiry case in isolation, outer timeout 540 seconds | 1 | 0 | 0 | 0 |

| Explicit outcome collector, 2 selected native cases, outer timeout 300 seconds | 1 | 1 | 0 | 0 |

No test is xfailed. The known large-history failure remains a normal failing assertion. TLS refusal was executed earlier on a3 and excluded from the latest 13-case selection; it was not skipped to produce a green suite. These are execution counts, not acceptance of unimplemented operational scenarios below.

The native 13-case summary was observed as `1 failed, 0 error(s) of 13 tests`. The older collector retained all 13 case JSON files but misclassified nine as not started because it depended on retained start lines and did not recognize the final `Failed:` footer. Its raw result is preserved. The report uses the observed native summary plus per-case evidence, not those incorrect lists. Native journald output was subsequently unavailable through the engine; credential-safe case files remain. The collector now stores explicit cleanup outcomes and classifies missing outcomes as unknown; missing evidence/logs cannot yield acceptance.

## Real callback and byte observations

| Scenario | Actual observation |
| --- | --- |
| DOCX/XLSX/PPTX | Browser plugin edited real Office documents; final status-2 callbacks committed one new immutable version. Garage bytes differed from the original ZIP, contained the inserted marker and matched the stored version SHA-256. |
| Two authorized DOCX editors | Odoo folder membership and FILE_WRITE checked for the second person; overlapping editor sessions generated signed history with both authorized IDs and one final version. This uses the private test page, not #230. |
| Duplicate/concurrent callbacks | Four parallel copies of the first authentic final delivery returned `[200,200,200,200]`; four later concurrent replays also succeeded. Version count stayed two (original plus one save), with correct actor/audit checks. |
| Temporary callback 503 | Real Document Server redelivered after 1.005 seconds; responses 503 then 200, fresh header/body JWT fingerprints and issue/expiry times. |
| HTTP 200/error 1 | One final delivery, no redelivery during a 15-second observation window; no saved version. This is a bounded negative control. |
| Retry exhaustion | Four deliveries total with 503/error 1, measured intervals 1.004, 2.005 and 4.003 seconds; no fifth delivery during the 15-second quiet window. No version claimed. |
| Garage unavailable | Real bucket proxy returned 503; actual redelivery recovered and created one version. Measured final-arrival interval about 10.18 seconds includes Odoo/bucket handling. |
| Conflict | Concurrent upload remained the current version; edited bytes became a separate conflict version. Total versions three, with actual content hashes and attribution checked. |
| Authentication | Genuine normal header/body signatures matched. Captured callbacks with absent, invalid, expired, inconsistent or wrong-key credentials were rejected. A large signed body-only duplicate did not add a version. No authentication bypass observed. |
| 370-second delayed transaction | Actual bytes staged before a PostgreSQL trigger delayed then raised serialization failure. Odoo refused expired credentials on its internal retry with 503. Actual DS redelivery had fresh JWTs and committed one version. Latest header iat/exp `1792915032/1792915332`; new iat `1792915405`, beyond original expiry plus leeway. |
| Invalid certificate | Actual pinned Document Server refused a self-signed HTTPS conversion source with download error -4 before any source GET. This is not an Odoo TLS-fetch or full ingress proof. |

Selected bytes from the 13-case comparison:

| Document | Bytes | SHA-256 (equal in Garage and immutable version) |
| --- | ---: | --- |
| DOCX concurrent callback case | 58553 | `26fb90e6188f6152d34b3cd2f510ed66eabb37b48bdebf2e382de4ba76758974` |
| XLSX | 11190 | `a0774016bd0e75dc50bb7fd8fd229473d1cb648dd30f2dae02ac82d8c3479e56` |
| PPTX | 33352 | `b9af753bd3393bb6a51bcb1f5fc2bb85fb27d2f4f1334e1939083df2393176b3` |

All successful normal saves have version count two and a marker in actual saved Office XML. Audit entries use source `api`, callback user unset, and the version actor is the verified last editor. These bytes are native editor outputs, not synthetic final-save responses.

## Findings and reproduction

### P1: long callback history is incompatible (#171, coordinated with #203)

Reproduce with `test_docx_many_editors_header_trimming` using the selected-case command in [README](README.md). Twenty-seven browser editor sessions create 27 native history changes. The stress participants are synthetic DS identities; the separate authorization test is not substituted for this load case.

On the latest comparison, the signed body JWT was 15232 bytes and retained 10941 bytes of history/27 changes. The header was 696 bytes; its signed history and the unsigned callback history were `{}`. Both JWT signatures verified, but their authenticated fields differed. Odoo returned HTTP 403/error 1; session stayed open and only the original version existed. Both JWTs still appeared with JWT_IN_BODY=false. Simply setting that flag is not a fix.

The pinned sender signs the body before trimming and regenerates only the header afterward: [DocsCoServer.js lines 718-734](https://github.com/ONLYOFFICE/server/blob/v9.4.0.1/DocService/sources/DocsCoServer.js#L718). [canvasservice.js near line 993](https://github.com/ONLYOFFICE/server/blob/v9.4.0.1/DocService/sources/canvasservice.js#L993) drops history/changesurl when authorization exceeds its threshold. Callback verification at `src/core/modules/sol_laboratory/services/onlyoffice_jwt.py:70` deliberately rejects unequal fields. This is safe rejection, with potential loss of automatic save delivery; it is not an authentication bypass.

Owner-reviewed options: an upstream signing correction/new pin, or a narrowly specified canonicalization of only upstream's known trimmed fields while verifying every token and binding key/status/download URL/users/actions strictly. Do not discard a token or ignore arbitrary field mismatches. No production fix was made here.

### P1: declared callback/retention settings do not reach workers (#203)

The fresh comparison container declares exact settings from 5b in NODE_CONFIG, JWT_IN_BODY=false and the handoff resource/logging flags. Run `python3 -m tools.onlyoffice_integration.probe_runtime` against the isolated project. Actual docservice PID 1143 and converter PID 1154 have no NODE_CONFIG. Their disk configuration aggregate shows callback inactivity/whole-cycle `10m` and `expire.files=86400`, rather than `21m`/`604800`. Native supervisor startup sanitizes inherited variables; container environment inspection alone missed this.

At 5b, `tools/infrastructure/onlyoffice/start.sh:9` only exports NODE_CONFIG before invoking the same upstream entrypoint at line 43. Agent 2 subsequently reported reproducing the missing worker variable and default 10-minute/one-day values with the full wrapper, and is preparing an owner fix. That full-wrapper execution is attributed to Agent 2; it was not executed by this harness. The local declared Node-contract comparison is demonstrably ineffective. Proposed fix for the infrastructure owner: persist a secret-safe merge into ds-readable runtime configuration or explicitly propagate the required settings to supervised workers, then assert worker settings and exercise the real timing/retention envelope. Do not accept seven-day recovery or the 21-minute budget from a declaration alone.

### Resolved P1: double-encoded callback capabilities (#171)

The original base leaked a synthetic double-encoded capability in diagnostics. On official a3 the regression passes normally: raw/single/double/mixed-case/malformed paths, bounded/idempotent processing, exception chains, cached tracebacks, background exceptions, watchdog stacks and real HTTP logging were exercised. Correlation metadata and unrelated diagnostics remain usable. The 24 pure checks and 38 native HTTP/logging checks passed. No callback production code was edited by this harness.

### Runtime logging

Every completed latest real case reported the actual callback capability, shared secret, JWTs and saved URL absent from its Odoo subprocess logs, including the failing history case. Default Document Server error logs previously exposed callback capabilities and JWT-like fragments; raw values were not copied into shared reports. With DS_LOG_LEVEL=OFF and NGINX_ACCESS_LOG=false, the available fresh docservice/converter logs were both zero bytes. This is evidence of those sinks being quiet, not proof of privacy across ingress, Loki, APM or CDN. The HTTP adapter did not apply the full #203 nginx error-log patch.

## Deadlock investigation and safe stop

The original slow-case harness had a lock inversion: the relay callback held `relay.lock`, then called committed setup and waited for Odoo `Registry._lock`; the main test held the registry lock and waited for `relay.lock` in `final_events`. Native thread stacks confirmed the cycle. PostgreSQL showed idle sessions, no active SQL delay, and the trigger sequence `is_called=false`.

Before termination, process tree, PID ownership, seven-thread SIGQUIT stacks, logs, database locks/activity and trigger state were captured under `.local/onlyoffice-agent4/full-a3/deadlock/`. Only approved runner host PID **551964** (container PID 1) and owned child **557684** (container PID 12) were stopped. SIGTERM/graceful stop sufficed; no SIGKILL escalation was needed for that runner. Exit was 130. Both PIDs disappeared, former database sessions/locks were gone, and the process-local registry lock ceased to exist. PostgreSQL, Garage, Document Server and unrelated agent services were not stopped.

Preserved runner: `medilab171-agent4-security-deadlock`; database: `medilab171agent4_deadlock`. The failed attempt completed eight tests, blocked on one and never started three. It is not reported as a complete passing run.

The corrected test installs the trigger on the main thread and uses a bounded ready/release rendezvous before callback forwarding. The affected case then passed alone with an explicit 540-second outer timeout and again in the 13-case cohort. A separate completed Garage setup hit a Podman Compose attach hang; only its stale client PID 883062 required SIGKILL after its setup container had exited 0. No active application/test service was killed in that cleanup. Detached polling prevents repeating that unbounded attach path for acceptance runners.

## Restart and retained-byte evidence

Signed getForgottenList/getForgotten commands retrieved three actual failed-save DOCX outputs before and after an owned Document Server restart. All three downloads returned 200, retained their exact hashes/sizes and contained editor markers. Evidence: `full-a3/recovery-before.json`, `recovery-after.json`, `recovery-comparison.json`. The committed read-only `forgotten_probe.py` was also executed afterward: all three outputs remained downloadable with markers. No forgotten bytes were deleted. All relevant volumes and databases remain preserved.

This restart occurred after these outputs were already forgotten, not while an unfinished edit was dirty. It used the older 10-second stop default and escalated to SIGKILL, not the proposed 1890-second helper. Fresh retrieval URLs were used afterward. It proves those retained outputs survived this local restart, not graceful active-save drain, old signed-URL continuity, seven-day retention, node-loss recovery or successful operator import. Agent 2's independent infrastructure proofs are not counted as online editing acceptance.

## Remaining unexecuted acceptance scenarios

These are eight scenario groups, not skipped unit tests or passing model substitutes:

| Scenario group | Ownership / classification |
| --- | --- |
| Full TLS start.sh/CA, actual callback ingress and effective corrected worker settings | #203; P1 acceptance blocker; environment fixture incomplete |
| Dirty concurrent XLSX/PPTX editing and restart during an unfinished edit or pending long callback under the 1890-second drain | #171/#203/#230; P1 integrity acceptance blocker; not executed |
| Actual Odoo transport outage and interrupted native output stream, full worker/caller/proxy/900-second-fetch envelope | #171/#203; P1 acceptance blocker; measured 370-second retry is narrower |
| Missing forgotten bytes, node/volume loss, seven-day retention, operator recovery and old signed-URL continuity in the joined stack | #203; P1 recovery acceptance blocker; no destructive experiment performed |
| Real CNI origin/egress restrictions, redirects and metadata/private-network isolation | #170/#203; P1 security acceptance blocker; local origin checks do not establish deployment policy |
| Released #230 editor page, Sync interaction and two authorized people across all Office types | #230/#170; P1 combined-flow acceptance blocker; private harness page only |
| Ingress/Loki/APM/CDN credential sinks and upstream nginx error paths in the full wrapper | #171/#203; P1 privacy acceptance blocker; available Odoo/DS sinks only |
| Failure alerts, terminal recovery classification and operator escalation in the joined environment | #203/#230; P2 operational acceptance gap; not executed |

Branches can enter a combined test environment after owners address/review the two P1 findings. They are not cleared for combined release, staging or production acceptance. No branch was pushed, no PR/issue mutation was made, and no deployment occurred. GitHub API identity was verified as KietPham-VN with a command-scoped stored token; Git metadata was verified independently.

## Related documents

- [Repeatable harness commands](README.md)
- [Sanitized committed evidence](evidence/2026-10-25/summary.json)
- [Laboratory files specification](../../docs/specs/laboratory-files.md)
