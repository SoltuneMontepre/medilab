# CloudBeaver security and peer review

Production remains **NO-GO**. This assessment supplements the [strict implementation review](cloudbeaver-review.md) and [operator recovery checklist](../workflows/cloudbeaver-recovery.md#operator-evidence-checklist). PR #293 must remain Draft and issue #286 open until production acceptance is reviewed. No production changes were made.

## Findings

The manual [CodeRabbit full review](https://github.com/SoltuneMontepre/medilab/pull/293#pullrequestreview-5644801185) covered base `4594a23` through `3d5571e`. All five inline findings were independently checked. No new P0/P1 defect was established; the six earlier P1 corrections remain documented in the strict review.

| Priority | Verified finding | Correction and evidence |
| --- | --- | --- |
| P2 | Connection merge removed explicit JSON `null` properties, including nested members | Exact-image regression failed before the change; `serializeNulls()` preserves these members along with unknown properties. Existing connections and credential stores remain untouched |
| P2 | Preflight treated successful `stat ... || true` as installation-file availability | Each required file now has metadata or an explicit missing marker; all three must be present. Tests cover zero through three files, partial output and failed exec without reading file contents |
| P2 | Kubernetes rejection assertions could pass while initialization was merely pending | Wait for a nonzero init exit plus the expected guard reason, or a real kubelet readiness-failure event after application state is established. Service/EndpointSlice/ingress rejection assertions remain |
| P2 | Unbounded container commands could stall regression execution | A 600-second default timeout and 180-second guarded-exit wait produce redacted failures; unit tests verify the boundary and that arguments/output are not exposed |
| P2 | A failed post-login identity request left a stale latch after later successful verification | A deterministic HTTP regression fails before the correction. Clear the latch only after the expected cached identity and both protected queries succeed. Rejected login remains latched; no account or password is changed |
| P2 | Label-only preflight missed unlabelled consumers of the workspace PVC | Inventory all same-claim Pods, including pending, terminating, init and ephemeral consumers and read-only/writable mounts. Add Job/CronJob controller inventory to the operator checklist. ReadWriteOnce is not exclusive writer protection |
| P2 | Rollout instructions assumed the optional Argo parent necessarily owns the live child | Require verified live declarative ownership. Ansible defaults root Application creation to false and can leave an external installation untouched. No candidate merge until a reviewed owner can deliver the hold |
| P2 | The application Pod inherited an unnecessary Kubernetes service-account token | Set `automountServiceAccountToken: false`; neither application nor bootstrap calls the Kubernetes API. The real Pod fixture verifies no projected API token and still completes the application lifecycle |
| P3 | Provisioning diagnostics omitted safe blocking categories | Fixed messages identify symlinks, duplicate IDs and absent credential keys; other exceptions print only the class. Raw parser messages can expose JSON/credentials and are deliberately excluded. Canary regressions verify redaction and unchanged files |
| P2, unresolved upstream | Local authentication uses fast MD5-derived credentials | Compatibility is verified below. Preserve existing credentials and the required wire protocol; review upstream authentication migration separately. No suppression or remote finding dismissal was performed |

## Three MD5 findings

Semgrep's Java rule flags `infra/cluster/cloudbeaver/bootstrap/Authentication.java`; two Python rules flag the same `hashlib.md5` call in `tools/cloudbeaver/runtime.py`. These are two call sites, not three separate implementations.

| Rule | Assessment | Disposition |
| --- | --- | --- |
| `java.lang.security.audit.crypto.use-of-md5.use-of-md5` | Uppercase MD5 of the UTF-8 password is required by CloudBeaver 26.2.2's local-login wire protocol. Generic signature/HMAC advice does not apply to this call. The password-equivalent token and upstream fast credential storage remain genuine security limitations | Retain compatible call; keep the upstream P2 risk visible for security review |
| `python.lang.security.insecure-hash-algorithms-md5.insecure-hash-algorithm-md5` | Synthetic regression client implements the same required protocol. It introduces no production password store | Retain to test actual compatibility; not a new production storage defect |
| `python.lang.security.audit.md5-used-as-password.md5-used-as-password` | Overlaps the Python call above. A classification as newly introduced password storage is a contextual false positive: the call constructs a wire credential. This does not make the upstream storage scheme strong | Document the distinction; do not mark the remote finding false positive or accepted without owner review |

### Verified protocol and storage

Source was checked at immutable CloudBeaver commit `4cd0be998ea40b03d4e6a29e12bc9f139ba0d080`, matching 26.2.2. The official [browser authentication service](https://github.com/dbeaver/cloudbeaver/blob/4cd0be998ea40b03d4e6a29e12bc9f139ba0d080/webapp/packages/core-authentication/src/AuthProviderService.ts#L65) uppercases MD5 for credentials whose provider declares `hash`. The [local provider](https://github.com/dbeaver/cloudbeaver/blob/4cd0be998ea40b03d4e6a29e12bc9f139ba0d080/server/bundles/io.cloudbeaver.service.security/src/io/cloudbeaver/auth/provider/local/LocalAuthProvider.java#L50) compares the encoded client value after applying the user-identifier-dependent hash. [Bootstrap account setup](https://github.com/dbeaver/cloudbeaver/blob/4cd0be998ea40b03d4e6a29e12bc9f139ba0d080/server/bundles/io.cloudbeaver.service.security/src/io/cloudbeaver/service/security/db/CBDatabase.java#L318) hashes the supplied administrator password before credential provisioning. [Credential persistence](https://github.com/dbeaver/cloudbeaver/blob/4cd0be998ea40b03d4e6a29e12bc9f139ba0d080/server/bundles/io.cloudbeaver.service.security/src/io/cloudbeaver/service/security/CBEmbeddedSecurityController.java#L1267) applies the provider's encryption function before storing the value.

The exact image's bundled classes were also inspected using `javap -c -p`, without launching CloudBeaver or mounting any workspace. `AuthPropertyEncryption.hash` delegates to `SecurityUtils.makeDigest(userId, value)`. That function feeds the UTF-8 identifier and client value into MD5; `ECRYPTION_ALGORYTHM` is initialized to `MD5`. The stored local credential is therefore a fast username-dependent MD5 of the already MD5-encoded password, rather than a modern adaptive password KDF. This creates an offline dictionary-attack risk if credential records are compromised. MD5 collision attacks are not the primary password risk here.

Replacing only the client hash with SHA-256, scrypt or a signature would break authentication and leave the upstream storage function unchanged. A compatible upstream upgrade/authentication migration requires separate design, saved-credential validation and approval; changing existing passwords or H2 records is outside this recovery. No unsupported claim is made about every historical account's provenance.

The regression suite uses fresh isolated workspaces to submit raw, SHA-256 and scrypt wire values; each is rejected, while the original MD5 login still succeeds, exactly one administrator remains, and the original password survives restart. A separate Unicode/special-character password authenticates through both the Java probe and Python client before and after restart. These executed tests complement source and bytecode evidence; they do not inspect production passwords.

### Credential boundary

The probe sends its password-equivalent hash only to `127.0.0.1`, does not log it and stores its session cookie in a private ephemeral file. The Secret remains accessible to the trusted container/runtime and exec probes; removing variables before the application launch reduces accidental application inheritance, not the container's trust boundary. HTTP on loopback assumes the Pod/node is trusted. Private cookies, workspace seeds, credential files and cold archives remain sensitive. TLS protects operator inventory requests. Readiness authentication can create normal session/audit writes; production diagnostics never initiate login.

## Lifecycle and rollout assessment

The guard accepts completed runtime plus nonempty H2 as a configured candidate, not proof of a valid administrator. Authentication and protected H2-backed lookups provide the usability gate. Unknown history, an interrupted marker or missing completion state blocks bootstrap. No setup retry, account repair or credential reset is hidden in readiness. Missing-runtime recovery requires trusted same-installation evidence on a cold clone.

`WRITE_DELAY=0` targets the same existing H2 path. Prior rapid-kill experiments and the regression suite establish improved acknowledged-write survival in the tested environment; they do not establish power-loss safety or production storage performance. Extra synchronous I/O, disk exhaustion, hardware flush behavior and node-local volume loss remain operational risks. Reverting Git does not undo H2 state or this persistent setting.

The root launcher and UID/GID 8978 match the actual image. A lifetime advisory `flock` survives the launcher's UID switch; init preparation uses the same lock. An unguarded process can ignore it, so backup requires every writer/controller accounted for and cleanly stopped. Abrupt termination and replacement are tested; the production node, filesystem and termination behavior remain unverified. Argo `Prune=false,Delete=false` must be applied to the existing live claim before rollout; it does not protect namespace/manual deletion, unrelated writers or storage loss.

The runbook now inventories unlabelled consumers and dormant controllers and conditions automation holds on verified ownership. Neither a feature-branch push nor Draft review authorizes merging to the watched `main` revision. The cold-backup restore rehearsal, scenario-specific B/C repair and final GitOps rollout all require explicit approval. No production context is available; the sanitized preflight exits 1 with `selected context absent` and `production_changes:false`.

## Executed validation

The complete exact-image container/API/unit suite passed **43 cases** in 239.234 seconds (47 discovered, four Kubernetes cases explicitly skipped for the separate cluster stage). Raw/SHA-256/scrypt protocol rejection and Unicode password compatibility also passed in a separate targeted run: two cases, 53.794 seconds. The null-preservation and uncertain-login-latch regressions each failed against the previous implementation before their fixes. Ruff lint/format, Python compilation, ShellCheck, actionlint, diff checks and 95 relative documentation targets pass. The operator shell examples were syntax-checked without production execution.

The strengthened real Kubernetes suite passed **four cases in 230.437 seconds**, including cleanup. It verifies actual guard/probe rejection, Service/Traefik exclusion, the disabled API-token mount and unlabelled read-only/writable consumers. An initial run correctly remained blocked but failed because the new test expected the wrong guard reason for an existing attempt marker; the corrected reason was verified from the disposable Pod log before the complete rerun. Additional HTTP fixtures reject disabled accounts, string-valued enabled flags and an unavailable connection registry without repeating login.

The independent Semgrep 1.182.1 scan ran 211 Java/Python rules on 22 targets with zero errors and exactly the three documented MD5 findings. The staged-patch Gitleaks scan found no leaks. A whole-working-tree scan reported three existing generic-key matches outside this PR: a numeric kube-apiserver toleration flag, the public Sonar project identifier and a synthetic laboratory-test password. These were inspected without printing values; no repository allowlist was added. Scanner findings remain visible; no rule or required CI gate was weakened. See the final-head CI results on the PR for the real Kubernetes rerun and the complete workflow status.

## Analysis limitations

CodeRabbit reported five inline findings and a docstring-coverage warning. The warning is not an executed repository quality gate; automatic generation of repetitive docstrings would conflict with the repository's sparse-comment convention. Meaningful diagnostics and behavior tests take precedence. Its Description, Linked Issues and Out of Scope subchecks were labelled passed but explicitly skipped. The manually requested review did not enable automatic review or autofix. Threads are left for reviewer verification, not automatically resolved.

CodeRabbit's Checkov invocation failed for `kustomization.yaml` and `service.yaml`; this is a tool failure, not a successful analysis. An independent Checkov 3.3.25 scan of those raw files produced one default-namespace warning; the rendered Service is in `medilab`, so that raw-file warning is inapplicable after Kustomize. The full rendered scan initially reported 76 passed and 15 failed policies, with zero parsing errors. Disabling the unnecessary service-account token improves this to **77 passed and 14 policy findings**; none was suppressed.

The remaining policy findings are explicit P3 hardening recommendations/limitations: image digest and pull policy (`CKV_K8S_43`, `15`); CPU limits (`11`); image-compatible pod/container security context, privilege escalation, NET_RAW/capability reduction, root UID and writable root filesystem (`20`, `30`, `28`, `37`, `29`, `22`, `23`, `40`, `31`); Secret files instead of environment variables (`35`); and network isolation (`CKV2_K8S_6`). The image's root launcher needs ownership changes and UID transition, its supported bootstrap consumes environment variables, and network rules need the actual database/ingress topology. These require separately validated hardening rather than mechanically applying every scanner suggestion. Readiness is not a substitute for NetworkPolicy or RBAC. Versioned tags, secret-bearing environment and Pod/node trust remain security risks; no vulnerability-free image claim is made.

 Sonar's wrapper previously passed while its actual scan was path-filtered out; no PR Sonar quality gate is established. The unauthenticated Sonar Cloud quality-gate API also returned HTTP 404 for PR 293 (component not found), not an OK result. Final exact-head CI, independent scanner results and reviewer responses are recorded on [PR #293](https://github.com/SoltuneMontepre/medilab/pull/293/checks). A green workflow is not proof that every analysis executed or that production data are intact.

## Related documents

- [Strict review and test baseline](cloudbeaver-review.md)
- [Initialization evidence and medilab-past comparison](cloudbeaver-initialization.md)
- [Recovery decision tree and operator checklist](../workflows/cloudbeaver-recovery.md)
- [Cluster](../infrastructure/cluster.md#cloudbeaver)
