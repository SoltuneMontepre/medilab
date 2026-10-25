# Independent callback verification results

Reviewed base: `fa8031db9eee3108211d771e09a57f20c038e4ad`.

Verification date: 2026-10-25 UTC. Local runtime: Linux `7.3.0-4-cachyos`, x86_64, glibc 2.44. The executed contract checks use the existing Python 3.12 environment and PyJWT 2.15.1. The preflight command used system Python 3.14.8.

## Executed

The local contract suite ran 22 cases: 21 passed and one expected failure reproduced the redaction finding below. Valid/invalid and expired JWTs, mixed header/body credentials, document-key tampering, large history/users, synthetic trimming, SSRF origin checks, encoded paths and diagnostic redaction were exercised against production service code. No local JWT authentication bypass was observed.

Python compilation, Ruff checks/formatting and Node syntax checking were run for the new harness. The Compose YAML was parsed and checked for the isolated project, absent host ports and exact expected Document Server pin. This is static configuration validation, not an engine-level Compose or image verification.

Real-service execution was blocked before startup:

| Check | Observed result |
| --- | --- |
| `gh auth token --hostname github.com --user KietPham-VN` with inherited token variables cleared | No stored token returned; exact API identity could not be verified |
| Local TCP socket creation | `PermissionError`, errno 1, before bind |
| Docker local-socket health check | Exit 1; Docker is a Podman compatibility command, which fails on a read-only runtime directory |
| Local rootless Podman socket | Connection refused/blocked |
| Registry lookup using local curl | DNS resolution failed |

No shared authentication or global Git configuration was changed. No services belonging to another worktree were stopped or modified. No deployment, push or remote GitHub write was performed.

The expected image is `onlyoffice/documentserver:9.4.0.1@sha256:3ab6ebc7c605e5a32b7ae3ff19daed4925090245acc8100ce2230bd766c88212`. The registry digest, platform manifest, actual image ID and Document Server runtime were **not independently verified** in this execution. No actual Document Server retry, JWT redelivery, edited Office bytes or saved bucket version is claimed. All ten opt-in real-service cases remain unexecuted, and the stack/browser build has not been validated by a container engine.

## Reproduced finding: double-encoded diagnostic reference

`src/core/modules/sol_laboratory/services/editing_callback_logging.py:23` detects callback references after one `unquote()`. Its request-line check at line 32 does the same. Outside request context, a watchdog record containing a callback URL encoded twice is returned unchanged at lines 36–37. An alphanumeric capability remains readable in the diagnostic.

Reproduction: the `test_double_encoded_callback_reference_is_redacted` case creates a normal `logging.LogRecord`, percent-encodes a synthetic callback URL twice, runs the actual `EditingCallbackFilter`, and asserts that its capability is absent. The assertion fails. Singly encoded references and exception chains pass. This demonstrates a filter gap; whether a real upstream component emits such a diagnostic remains unmeasured.

Proposed fix for the production owner: use a shared, bounded normalization function for both the request line and formatted diagnostic/exception text. Check each decoding level until stable, with an explicit size/depth bound and conservative redaction if the bound is reached. Add direct, singly/doubly encoded, mixed-case escape and exception-chain regressions. Preserve the unrelated-diagnostics checks. No production change was made here.

## Required coverage and remaining gates

| Area | Available coverage | Remaining evidence |
| --- | --- | --- |
| Authentication and expiry | Executed pure-service checks; existing `test_laboratory_editing_http.py:117`; new captured-delivery controls | Execute actual Odoo refusals, browser/editor authentication and real callback consistency |
| Large history/users and trimming | Executed large payload and synthetic mismatch checks | Observe pinned upstream trimming and header limits; prove full emitted body and both signatures remain consistent |
| Final save and duplicate versions | New real DOCX/XLSX/PPTX and duplicate controls | Execute all cases and inspect saved hash/version evidence |
| HTTP 503 and 200/error 1 | New real-redelivery and negative controls | Measure actual schedule, quiet windows and finite exhaustion; expiry across fresh deliveries remains untested |
| Concurrency and conflicts | Existing HTTP race at `test_laboratory_editing_http.py:248`; new concurrent duplicate and conflict controls | Execute with real service; concurrent initial save race still relies on existing fixture tests |
| Bucket outage and streaming interruption | New real Garage-outage control; existing interrupted-stream HTTP test at line 103 | Execute real-service outage; interrupt an actual Document Server output stream |
| Odoo unavailable | Relay injects HTTP 503 only | Test actual Odoo transport refusal and process recovery |
| Document Server restart and forgotten bytes | No automated case added | Restart during pending save; prove retained/missing forgotten bytes, expiry of saved URLs and recovery classification |
| Long fetch/JWT expiry and worker/caller budgets | Existing HTTP retry-expiry test at line 297; existing fetch deadline test | Measure real elapsed fetch, JWT revalidation, worker kill, ingress and caller timeouts; approve whole-cycle budget |
| Origins/SSRF/redirects | Executed origin checks; existing real local redirect fixture in `test_saved_documents.py:70` | Execute through pinned Document Server and validate actual network isolation; no network policy changes made |
| Redaction/encoded URLs/upstream logs | Executed local logging checks and reproduced double-encoding gap | Fix production gap; validate real Odoo/ingress/Document Server log sinks and access control |
| Invalid certificates | New real self-signed HTTPS conversion-source refusal case | Execute pinned service test; actual Odoo saved-document HTTPS fetch also remains unexecuted |

#171 still requires the real-service compatibility evidence above and owner review of the diagnostic finding. #203 still requires isolation, retained bytes for the promised recovery period, alerts, the measured timing envelope and a tested recovery runbook, including an explicit unrecovered outcome when bytes are missing. #170's operational/editor prerequisites and #230's editor feedback remain outside this harness; their issue state could not be fetched under the required GitHub identity. No staging or production acceptance is established.

## Related documents

- [Harness instructions](README.md)
- [Laboratory files specification](../../docs/specs/laboratory-files.md)
- [Pinned upstream retry path](https://github.com/ONLYOFFICE/server/blob/v9.4.0.1/DocService/sources/canvasservice.js)
- [Pinned upstream signing utility](https://github.com/ONLYOFFICE/server/blob/v9.4.0.1/Common/sources/utils.js)
