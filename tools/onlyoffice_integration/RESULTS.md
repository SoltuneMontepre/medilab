# ONLYOFFICE P1 remediation verification

Verification executed on 2026-10-25 UTC against isolated local resources. Both P1 defects are fixed and independently verified with native service evidence: the large-history callback now saves exactly one new immutable version, and actual supervised workers apply the approved configuration across restarts and recreation. Acceptance below distinguishes native service execution, test fixtures and release scenarios that remain unexecuted.

## Sources and runtime

| Component | Verified identity |
| --- | --- |
| Preserved verification baseline | `fec03154ceac7bb1ce9a637b9f0c077d5c3374ed` |
| Callback receiver and double-encoded URL fix | `a3cec45f17f2429f99ae8556391c5750e38cc80a`; strict JWT verifier unchanged |
| Sender correction | `b4e973fcf4ad6829f4b21c0104d549c54c65b98d`, integrated as `f4b600c` |
| Supplemental malformed payload regressions | `21c84834ab854b2d66ea3a46b3d4c48159b09ce2`, integrated as `ab1a19f` |
| Worker configuration fix | Existing `c3f9dd1817ca43c898e9ef3f4b3dd6570a41b7f6`, integrated as `e188679`; effective-policy bootstrap integrated as `a7cb817` |
| Native cache retention fixture | `c0871ae`, integrated as `01cf9cf` |
| Runtime-file drift detection | `775a5a798db8a28ccc998cd1ff49d26bd207f689`, integrated as `bc97c8c` |
| CI regression wiring | `41f6046` |
| Document Server image | `docker.io/onlyoffice/documentserver:9.4.0.1@sha256:3ab6ebc7c605e5a32b7ae3ff19daed4925090245acc8100ce2230bd766c88212` |
| amd64 manifest / image ID | `sha256:e231bc62da8c1f0c1f78188f8c7e17e67716f38955d0ad1d703cf911ad6db84b` / `9f1f9ada40561752ba2597da8fe6e51fe7e09ba2b76cebdb4377ce004d88e5a3` |
| Package / command API | `9.4.0-129` / `9.4.0.129` |
| DocService executable SHA-256 | `556df4aab7b1a87123046a4459baee34e60f57deaf7bcd189bccd6f271bd8fcb` |
| Converter executable SHA-256 | `ac76144203fd4e8fdee4cccac976697e87ec9b67b7bdf572e6ea1288524a8f80` |
| Odoo real-service runner | `medilab-odoo:issue-171-callback`, image `d1e0a91af55b9176fdcf60125a1f3aa40a99e3e83ac779a857eae0b0afa06a19`; Odoo `20.0-20260926`, PyJWT `2.15.1` |
| Separate native HTTP/logging runner | `medilab-odoo:local`, image `1a49b35bebebbe75ebe5af7dfbabf2a660f1a81af24afeb3568bec87a8f7823c` |
| Garage | `2.4.1`, digest `sha256:9c96caa2612d3411acc5b0e6701fb238dbfba33e533a6d7d3d811a4b12d0d020` |
| PostgreSQL / browser / Node | PostgreSQL `18.6`; Playwright `1.56.1` with Chromium; packaged Node `20.20.0` |
| Committed worker settings SHA-256 | `4e7faa0e26e8baa3b4ad3ef6912f1a38acd2b9f1e423995f07fe4c77ba77d666` |

The joined worktree is `/home/leon/Projects/medilab-wt-onlyoffice-p1`, branch `fix/171-203-onlyoffice-p1`. It starts at the full verification baseline and selectively incorporates the six #203 deployment commits, preserving their original branch and all earlier #171 history. Main's unrelated `questions/laboratory.md` edit and the #206/#230 worktrees were left untouched. All new commits use author and committer `KietPham-VN <153413668+KietPham-VN@users.noreply.github.com>` without attribution trailers.

[Runtime identity](evidence/2026-10-25/p1/fixed/runtime.json) and the [source manifest](evidence/2026-10-25/p1/fixed/source-manifest.json) record the exact running binaries and mounted source hashes. The pinned executables were not modified. The source manifest captures the mounted harness changes that were uncommitted when the joined run started. Subsequent bounded HTTP-startup retry handling and runtime-file fingerprint checks have separate history-rerun and full-wrapper evidence; they are not silently attributed to workers that started before those changes.

Only `/run/user/1000/podman/podman.sock` was used. The new projects have no public host ports or production connections. Test credentials and certificates are isolated fixtures. Original services, databases and volumes remain preserved. The 12 new joined-stack fixture services were stopped after verification; Document Server exited 0 with the 1890-second budget, and browser fixtures exited 143 on SIGTERM. All state and failed-attempt records remain preserved. [Owned fixture shutdown](evidence/2026-10-25/p1/cleanup/result.json), [full-wrapper fixture shutdown](evidence/2026-10-25/p1/worker/cleanup.json).

## Root cause and fix: large-history callbacks (#171/#203)

The defect is in the pinned sender's ordering. [DocsCoServer.sendServerRequest](https://github.com/ONLYOFFICE/server/blob/v9.4.0.1/DocService/sources/DocsCoServer.js#L718) creates the body JWT and initial header JWT. It then invokes [canvasservice.checkAndFixAuthorizationLength](https://github.com/ONLYOFFICE/server/blob/v9.4.0.1/DocService/sources/canvasservice.js#L993), which removes `changesurl` and replaces `history` with `{}` when the authorization token reaches 7168 bytes. Only the header JWT is regenerated afterward. The serialized body contains the trimmed fields and the stale body JWT signing the full history.

The exact baseline reproduction created 27 native editor history changes. Its final body JWT was 15229 bytes and signed 10941 bytes of history; the 695-byte authorization header and ordinary callback fields contained `{}` instead. Both signatures were valid. The byte-preserving relay delivered the mismatch to Odoo, whose `services/onlyoffice_jwt.py:verify_callback` rejected it with HTTP 403/error 1 before document fetch or version creation. Only the original immutable version remained. This establishes a sender payload mutation, rather than proxy truncation, JSON encoding or a signature bypass. `JWT_IN_BODY=false` did not prevent the pinned callback implementation from generating both tokens. [Baseline outcome](evidence/2026-10-25/p1/baseline/result.json), [sanitized delivery](evidence/2026-10-25/p1/baseline/callbacks/test_docx_many_editors_header_trimming.json).

`infra/cluster/onlyoffice/callback-signing.cjs` wraps the native exported sender. For callbacks carrying the native length checker, it calculates the header using the native tenant secret and signing helper, then runs that checker once before calling the unchanged sender. The native sender therefore signs both tokens over the finalized fields. Its body is then serialized and sent through the existing Document Server routing and the byte-preserving callback relay to `src/core/modules/sol_laboratory/controllers/laboratory_editing_callback.py`, then `services/laboratory_editing_callback.py` and the strict `services/onlyoffice_jwt.py` verifier. Its transport, timeout, retry, origin and signing implementations remain in use. No receiver comparison, token validation or authorization was relaxed. Save bytes and immutable version creation remain Odoo's existing code paths.

The implementation choice is a small bootstrap around the pinned packaged runtime: the image contains bytecode rather than editable JavaScript. It uses pkg's existing child-entrypoint mechanism, validates the exact executable hashes and module contracts, and refuses startup if the correction cannot be installed. Neither binary patching nor an unverified replacement image is involved. Internal status notifications have no history trimming and retain the original path.

The independent corrected real-service rerun is **PASS**: 27 browser editor sessions produced a 696-byte header and 673-byte body JWT signing the same trimmed history. Odoo returned HTTP 200/error 0, committed the session and created exactly one new immutable version. Its 58801 Garage bytes match stored SHA-256 `07e907b9a45fb402c09ff1b9e4bcc738ddb0ba74ce17f8e00e4b16278f8e1b69` and contain the browser marker; total version count is two including the original. [Executed outcome](evidence/2026-10-25/p1/history-retry/result.json), [saved-byte evidence](evidence/2026-10-25/p1/history-retry/callbacks/test_docx_many_editors_header_trimming.json).

Regression coverage includes the native 7167/7168-byte boundary, unchanged ordinary callbacks, failure before transport, signed malformed claims, wrong signatures, invalid tokens, stale/full versus trimmed token disagreement, and binding of key/status/download URL/users/actions/history. The receiver continues to reject mismatched payloads, including the original upstream failure shape.

## Root cause and fix: effective worker configuration (#203)

The pinned `/app/ds/run-document-server.sh:816` starts Supervisor through `service supervisor start`. `/usr/sbin/service:135` invokes the init script using `env -i`; its allowlist excludes `NODE_CONFIG`. Supervisor's native worker files set `NODE_ENV=production-linux` and `NODE_CONFIG_DIR=/etc/onlyoffice/documentserver`, but do not restore that override. Exporting it from the parent wrapper consequently had no effect on either actual worker. The baseline observed no worker `NODE_CONFIG`, `callbackRequestTimeout=10m` and `expire.files=86400`. [Baseline probe](evidence/2026-10-25/p1/baseline/effective-runtime.json).

The existing #203 fix already changes the Supervisor commands to launch `worker.sh`, which reads the committed policy after environment sanitization. The added `worker-bootstrap.cjs` runs inside the actual docservice/converter process using the packaged runtime, loads the original entrypoint, then checks the effective `config.get` values after ONLYOFFICE's runtime merge. It verifies every committed policy leaf and exact runtime identity. A per-PID attestation contains only approved non-secret fields, binary/settings hashes and the process start tick. `inspect_config.py` compares that evidence with the live process and settings, including converter children, and rejects absent, stale or drifting evidence even if the environment alone looks correct.

ONLYOFFICE also merges a runtime JSON file from its effective `production-linux` configuration. The drift check fingerprints that file's presence and bytes after startup and compares them with current disk state. A later live override change invalidates readiness and acceptance evidence; no active editing worker is killed. Its existing path and behavior are preserved, and raw runtime configuration is never reported.

The approved values remain unchanged: both callback timeout budgets are `21m`, cache retention is `604800` seconds, JWT is HS256 with a five-minute lifetime, retry intervals are finite 1/2/4 seconds, certificate verification stays enabled, metadata addresses remain disallowed and automatic assembly remains disabled. Parent environment declarations are not counted as effective runtime proof. [Actual worker policy](evidence/2026-10-25/p1/fixed/effective-runtime.json).

## Executed verification

Every test has an explicit status in the linked machine-readable evidence. Cohorts repeat some cases and must not be added together as distinct coverage. No failed assertion is xfailed or hidden by a skip.

| Suite / cohort | PASS | FAIL | SKIPPED | BLOCKED | Evidence |
| --- | ---: | ---: | ---: | ---: | --- |
| Exact baseline large-history reproduction | 0 | 1 | 0 | 0 | [Result](evidence/2026-10-25/p1/baseline/result.json) |
| Pure JWT/origin/logging contracts | 29 | 0 | 0 | 0 | [Every test](evidence/2026-10-25/p1/fixed/fast-tests.json) |
| Deployment and effective-policy contracts | 26 | 0 | 0 | 0 | [Every test](evidence/2026-10-25/p1/fixed/fast-tests.json) |
| Sender regression contracts | 7 | 0 | 0 | 0 | [Every test](evidence/2026-10-25/p1/fixed/fast-tests.json) |
| Separate native Odoo HTTP/logging cohort | 38 | 0 | 0 | 0 | [Every test](evidence/2026-10-25/p1/native/result.json) |
| Joined native Odoo JWT/HTTP/logging and real-service cohort | 75 | 0 | 0 | 0 | [Observed native summary and 15 real outcomes](evidence/2026-10-25/p1/fixed/result.json) |
| Final-source native JWT/HTTP/logging repeat | 60 | 0 | 0 | 0 | [Every native test](evidence/2026-10-25/p1/native-final/result.json) |
| Initial independent history attempt: HTTP child startup timeout, no test executed | 0 | 0 | 0 | 1 | [Startup result](evidence/2026-10-25/p1/history/result.json) |
| Independent real-service large-history rerun | 1 | 0 | 0 | 0 | [Result](evidence/2026-10-25/p1/history-retry/result.json) |
| Final-source real saves after owned Document Server restart | 4 | 0 | 0 | 0 | [Every test](evidence/2026-10-25/p1/post-restart/result.json) |
| Native aged-record retention fixture | 1 | 0 | 0 | 0 | [Result](evidence/2026-10-25/p1/worker/retention-native-fixture.json) |

The joined cohort completed with exit 0 and the observed native summary `0 failed, 0 error(s) of 75 tests`. All 15 real-service cleanup files explicitly record their test-body outcome as true. Long-run engine log rotation retained only 11 late native start entries, so that partial start map is not presented as a complete 75-name record. The final-source native-only repeat completed with exit 0, `0 failed, 0 error(s) of 60 tests` and all 60 individual statuses **PASS**: 22 JWT, 27 HTTP and 11 logging tests. Its evidence correctly sets real-service execution false; that cohort exercises native Odoo rather than claiming another Document Server run. Repeated cohorts are not added as distinct coverage.

The 62 fast tests are all PASS. This preserves the original 24 production security contracts and adds five malformed/large-history cases. The separate 38-case native cohort preserves all 27 HTTP and 11 logging cases, including double-encoded URLs, independent HTTP commit/rollback behavior, JWT expiry and background diagnostic redaction. These suites do not substitute for the real-service cases.

Kubernetes manifest validation is **PASS** for 14 core resources and **PASS** for 18 custom resources against pinned upstream schemas. Kubeconform initially reports 16 resource schemas **SKIPPED**: 15 are checked by the separate custom-resource validator; one unchanged base Odoo `Backup` remains explicitly **SKIPPED** outside this ONLYOFFICE change. This is offline schema validation, not cluster or CNI execution. [Validation output](evidence/2026-10-25/p1/worker/schema-validation.log).

## Real-service cases

Every case below ran against actual Odoo, pinned Document Server and Garage. Successful normal saves have two immutable versions including the original, matching bucket/version SHA-256, a marker inside real Office XML and the verified editor as actor. The conflict case has three versions and preserves the concurrent upload as current. Callback audit source is `api`, without attributing the callback to a browser-cookie user. The relay forwards native callback bytes unchanged; deliberate response injection and captured authenticated replay controls are identified by their cases.

| Case | Status | Observed result |
| --- | --- | --- |
| [test_docx_save_and_concurrent_duplicate_callbacks](evidence/2026-10-25/p1/fixed/callbacks/test_docx_save_and_concurrent_duplicate_callbacks.json) | PASS | Real DOCX save and concurrent first-delivery/later duplicate controls create exactly one new version |
| [test_xlsx_save](evidence/2026-10-25/p1/fixed/callbacks/test_xlsx_save.json) | PASS | Real XLSX save, 11191 verified bytes |
| [test_pptx_save](evidence/2026-10-25/p1/fixed/callbacks/test_pptx_save.json) | PASS | Real PPTX save, 33356 verified bytes |
| [test_docx_large_history_header_compatibility](evidence/2026-10-25/p1/fixed/callbacks/test_docx_large_history_header_compatibility.json) | PASS | Long-name editor case, consistent signed fields and saved bytes |
| [test_docx_many_editors_header_trimming](evidence/2026-10-25/p1/fixed/callbacks/test_docx_many_editors_header_trimming.json) | PASS | 27 native editor sessions, consistent trimmed tokens, HTTP 200/error 0, exactly one new 58803-byte version |
| [test_docx_two_authorized_editors](evidence/2026-10-25/p1/fixed/callbacks/test_docx_two_authorized_editors.json) | PASS | Odoo folder membership and FILE_WRITE verified for the second person; native signed history contains both authorized IDs |
| [test_docx_503_redelivery_has_fresh_jwt](evidence/2026-10-25/p1/fixed/callbacks/test_docx_503_redelivery_has_fresh_jwt.json) | PASS | Actual redelivery after 1.006 seconds, fresh token fingerprints/times, HTTP 503 then 200, one new version |
| [test_docx_200_error_one_does_not_retry](evidence/2026-10-25/p1/fixed/callbacks/test_docx_200_error_one_does_not_retry.json) | PASS | Deliberate HTTP 200/error 1 yields one delivery and no version; no redelivery in the 15-second quiet window |
| [test_docx_finite_retry_exhaustion](evidence/2026-10-25/p1/fixed/callbacks/test_docx_finite_retry_exhaustion.json) | PASS | Four HTTP 503 deliveries at 1.006/2.006/4.006-second intervals; no fifth in the 15-second quiet window and no new version |
| [test_docx_bucket_failure_recovers_on_real_redelivery](evidence/2026-10-25/p1/fixed/callbacks/test_docx_bucket_failure_recovers_on_real_redelivery.json) | PASS | Actual Garage proxy outage, real redelivery after 12.087 seconds including bucket handling, then one new version |
| [test_docx_conflict_preserves_concurrent_version](evidence/2026-10-25/p1/fixed/callbacks/test_docx_conflict_preserves_concurrent_version.json) | PASS | Concurrent upload remains current; editor bytes become a separate conflict version |
| [test_docx_real_jwt_expiry_on_transaction_retry](evidence/2026-10-25/p1/fixed/callbacks/test_docx_real_jwt_expiry_on_transaction_retry.json) | PASS | 370-second delay crosses JWT expiry; actual fresh-token redelivery after 372.763 seconds commits one version |
| [test_docx_callback_exceeds_default_worker_timeout](evidence/2026-10-25/p1/fixed/callbacks/test_docx_callback_exceeds_default_worker_timeout.json) | PASS | 650-second callback exceeds the old ten-minute worker default; fresh-token redelivery after 653.870 seconds commits one version |
| [test_docx_captured_delivery_authentication_controls](evidence/2026-10-25/p1/fixed/callbacks/test_docx_captured_delivery_authentication_controls.json) | PASS | Missing/invalid/expired/mismatched credentials refused; a large signed body-only duplicate creates no extra version |
| [test_docx_documentserver_refuses_untrusted_tls_source](evidence/2026-10-25/p1/fixed/callbacks/test_docx_documentserver_refuses_untrusted_tls_source.json) | PASS | Pinned server refuses an untrusted HTTPS conversion source with download error -4 before a source GET |

The 27-editor load case includes synthetic Document Server identities; it does not substitute for the separate two-person Odoo authorization case. These private test pages are not the #230 released editor page or Sync.

## Timing, lifecycle and retention evidence

| Native probe | Status | Actual observation |
| --- | --- | --- |
| Full TLS wrapper, effective worker policy before restart | PASS | Both native processes attested `21m` / `604800`; [before restart](evidence/2026-10-25/p1/worker/before-restart.json) |
| Owned container restart | PASS | Graceful stop exit 0, no OOM kill, new live workers with the same policy; [after restart](evidence/2026-10-25/p1/worker/after-restart.json) |
| Final committed full-wrapper fresh recreation | PASS | Both native workers run the final `775a5a7` policy check; `local.json` mode 0600, available worker logs zero bytes, graceful prior stop exit 0; [fresh startup](evidence/2026-10-25/p1/worker/final-fresh-start.json) |
| Owned container recreation | PASS | New live workers retain the exact policy and all three state paths retain fixture markers; owned markers removed; [after recreation](evidence/2026-10-25/p1/worker/after-recreate.json) |
| Runtime override despite correct environment | PASS | Both native executables reject the effective one-day override with exit 78 and credential-safe diagnostics; [drift proof](evidence/2026-10-25/p1/worker/native-drift.json) |
| Runtime file change after startup | PASS | Readiness refuses stale attestation while both active worker PIDs remain unchanged; original file restored; [drift proof](evidence/2026-10-25/p1/worker/native-drift.json) |
| Signed conversion through full TLS wrapper | PASS | Trusted HTTPS DOCX source converted to 1922 PDF bytes, fetched with certificate verification; SHA-256 `ab1bbceb34de830f0f24505cc51dfb56b69ea3595cecafaca43526f1ce99e738`; [TLS conversion](evidence/2026-10-25/p1/worker/tls-conversion.json) |

The joined stack also retained two actual failed-save DOCX outputs across an owned graceful restart: the 58550-byte and 58554-byte outputs remained downloadable with markers and identical hashes. Stop completed with exit 0 within the configured 1890-second budget, and the complete restart took 35.67 seconds. Both restarted workers attested the final policy and unchanged runtime-file fingerprint. [Restart and retained-byte comparison](evidence/2026-10-25/p1/fixed/restart-and-recovery.json), [before](evidence/2026-10-25/p1/fixed/forgotten-before.json), [after](evidence/2026-10-25/p1/fixed/forgotten-after.json). No forgotten bytes were deleted.

The TLS conversion is standalone; it does not exercise Odoo's TLS callback ingress. The restart/recreation probes did not interrupt dirty editing or claim an active-save drain. The production-linux runtime file path `/var/www/onlyoffice/Data/runtime.json` is preserved. File fingerprint checks detect drift; they are not continuous measurement of every in-process configuration read.

The actual joined callback exceeded the ineffective ten-minute default: a 650-second PostgreSQL serialization delay was followed by real Document Server redelivery after 653.869975 seconds. Responses were 503 then 200, both deliveries had consistent signatures, and the fresh JWT issue time `1792919543` exceeded the first expiry `1792919189` plus clock leeway. Exactly one new 58553-byte version was committed with marker and Garage SHA-256 `42272a58bfea0ffa0f4ce86e11e29f6f8d6c449bf420c6dae179d4ee5ceb8e1f`. This measured cycle demonstrates the worker's callback budget exceeds ten minutes, rather than relying on its environment declaration. [Executed delivery](evidence/2026-10-25/p1/fixed/callbacks/test_docx_callback_exceeds_default_worker_timeout.json).

After an owned graceful Document Server restart loaded the final bootstrap, the actual DOCX duplicate-delivery case, 27-editor history case, XLSX save and PPTX save all independently repeated **PASS**. Each created one new immutable version with matching Garage SHA-256, authorized attribution and a marker in real Office XML. [All four outcomes](evidence/2026-10-25/p1/post-restart/result.json).

| Save after restart | Bytes | Garage and immutable-version SHA-256 |
| --- | ---: | --- |
| DOCX with concurrent duplicates | 58552 | `b883a3e05948daa2a0f71b520e5136be2aa3d1e524b27c87dbd061422c60c642` |
| DOCX, 27 editor sessions | 58805 | `32a48b698b88038f0f021c4c8eb4853fe1a7852cb5ce389cb5765518d9e0535d` |
| XLSX | 11191 | `6b8ec89442293a35bae6b6657662eae93a3b03d80bb49f5e47e03a3d1bb79bf7` |
| PPTX | 33366 | `d38e900a9a74c9c5d62116274e889c8b63e0d1c26cea9451c842f837bfbbbc4a` |

The native aged-record retention fixture is **PASS**: a separate disposable process runs the pinned executable's actual task APIs and garbage collector with the unchanged `604800`-second policy. A two-day-old synthetic task and its filesystem bytes survive; an eight-day-old task and bytes are removed. The younger byte SHA-256 is `221e44cd02e7b7e4ce7ca406a1ff45a2364cffacca9d5c86d97072e1fb4084f4`. Its process-local Date override is restricted to fixture creation and restored before the native garbage collector runs. The network is disabled, no shared volumes are mounted, fixtures are cleaned, and both the 30-second native and 45-second outer deadlines complete with exit 0. [Executed fixture](evidence/2026-10-25/p1/worker/retention-native-fixture.json).

This establishes native expiration selection and filesystem deletion over aged fixtures. It does not establish seven elapsed days, live supervised-worker cron execution, task persistence or continuous recovery. Those remain separate release scenarios.

## Credential-safe logging

The available Document Server docservice/converter/example/metrics output and error sinks, nginx access/error sinks and container output are individually **PASS** in the [runtime log scan](evidence/2026-10-25/p1/fixed/upstream-logging.json): all scanned sinks were zero bytes and contained no JWT values or callback capabilities. The full TLS wrapper's latest conversion also retained zero native worker log bytes. The HTTP fixture applies the same nginx log suppression and production worker bootstrap while retaining its isolated HTTP transport.

Each completed real-service case checks its actual Odoo subprocess logs for the callback capability, shared signing secret, JWTs and saved-document URL. The native logging suite also exercises encoded/double-encoded paths, exception chains, cached tracebacks, watchdog/background diagnostics and useful correlation metadata. Available local sinks are the measured scope; ingress, Loki, APM and CDN sinks remain unexecuted release acceptance.

## Historical evidence preserved

The original verification result remains available in Git at `fec03154ceac7bb1ce9a637b9f0c077d5c3374ed:tools/onlyoffice_integration/RESULTS.md`; its sanitized evidence remains under [evidence/2026-10-25](evidence/2026-10-25/summary.json). On a3, it recorded 24 pure contracts, 38 native HTTP/logging checks and 13/14 distinct real-service cases passing. The one failing case was the large-history sender mismatch reproduced above. The original integration commit `27fa44c8436206765dd5bfa9f12099761af3f712` and its a3 cherry-pick `4b4bbff362f6534c032e92d9f4bb82037fb87c5e` are preserved. Prior 370-second expiry, actual DOCX/XLSX/PPTX Garage saves and forgotten-output byte evidence were not replaced with mocked claims.

The prior deadlock was a registry/relay lock inversion: a relay thread held `relay.lock` while requesting committed setup under `Registry._lock`, while the main test held the registry lock and waited for the relay. The corrected harness installs the PostgreSQL trigger on the main thread and uses a bounded ready/release rendezvous before forwarding. The new slow-case progress evidence observed the trigger sequence called and active PostgreSQL `PgSleep`; it was not stuck in registry setup. [Progress](evidence/2026-10-25/p1/fixed/long-callback-progress.json).

The initial new independent history attempt was **BLOCKED** during class setup: a one-second child Odoo health read timed out before any test began. The helper now retries both connection and read-timeout errors within its existing 45-second startup deadline. The retry uses a distinct guarded database and runner name while preserving the failed attempt; it is not a signature-fix failure.

The old interrupted attempt remains classified incomplete in the historical report. Its owned runner/database and prior recovery artifacts are preserved. New acceptance runners use detached engine polling with bounded commands and whole-run deadlines, avoiding the previous Compose attach hang. No unrelated application process or shared resource was stopped.

## Issue acceptance and remaining dependencies

Both P1 fixes are accepted for the measured local integration scope. This does not close either GitHub issue or grant combined staging/production release acceptance.

| Scope | Classification | Remaining acceptance |
| --- | --- | --- |
| #171 large-history P1 | Fixed and verified | Independent native callback, exact Garage bytes and exactly one new immutable version |
| #203 worker propagation P1 | Fixed and verified | Actual worker policy, restart/recreation, measured callback beyond ten minutes and native aged-record retention fixture |
| #171 double-encoded logging P1 | Fixed and verified | Preserved native and pure regressions |
| #230 released editor page / Sync flows | Not executed | Private harness page is not the released UI; two authorized people across all Office types remain a combined-flow gate |
| #206 integration and CI/release | Not executed | No changes to #206 implementation; joined Sync/API branch and remote CI/release acceptance remain separate |
| Staging / production release | Still blocked | Deployment-policy, recovery and operational gates below |

Remaining release scenarios are explicitly not passing test coverage:

| Scenario | Status / dependency |
| --- | --- |
| Dirty concurrent XLSX/PPTX and restart during unfinished editing or a pending callback under the full drain budget | NOT EXECUTED; #171/#203/#230 |
| Actual Odoo transport outage and interrupted output stream across the complete worker/caller/proxy/fetch timing envelope | NOT EXECUTED; #171/#203; native HTTP fixtures and measured delays are narrower |
| Missing forgotten outputs, node/volume loss, full seven elapsed days, operator import and old signed-URL continuity in the joined stack | NOT EXECUTED; #203; retained bytes and aged-record selection are narrower |
| Real Kubernetes CNI origin/egress policy, private-network/metadata isolation and actual ingress TLS callbacks | NOT EXECUTED; #170/#203; local origin/TLS probes do not establish cluster enforcement |
| Ingress/Loki/APM/CDN credential sinks | NOT EXECUTED; #171/#203; available local log sinks only |
| Failure alerts, terminal recovery classification and operator escalation in the joined environment | NOT EXECUTED; #203/#230 |
| Remote CI quality gate and release acceptance | NOT EXECUTED; local checks and CI wiring are not a remote CI run |

The intentionally chosen sender bootstrap retains upstream history trimming and strict receiver validation. Worker policy is loaded after the sanitized launch boundary and checked inside the native processes; runtime-file drift refuses readiness without terminating editors. Exact binary hashes make unsupported image upgrades fail closed.

No production secrets or credentials were changed. No branch was pushed; no PR was created or merged; no issue was closed; no production deployment was attempted.

## Related documents

- [Repeatable harness commands](README.md)
- [ONLYOFFICE infrastructure handoff](../../docs/infrastructure/onlyoffice.md)
- [Laboratory files specification](../../docs/specs/laboratory-files.md)
- [Preserved original verification evidence](evidence/2026-10-25/summary.json)
