# CloudBeaver recovery

Preserve the existing PVC, H2, accounts, settings, connections and credentials. Read-only diagnosis does not authorize recovery, Secret changes, workload restarts, merging a deployment revision or Argo CD sync. The [review report](../reports/cloudbeaver-review.md) separates local evidence from production facts.

## Read-only preflight

Use an explicitly authorized context on every request. Do not fetch credentials or change contexts merely to obtain access. The diagnostic helper performs selected `get`, `logs` and metadata-only `exec` operations; it never opens H2, prints passwords or raw configuration, logs in, or changes resources:

```bash
: "${CB_CONTEXT:?Set the approved read-only production context}"
: "${CB_KUBECONFIG:?Set the approved kubeconfig path}"
python3 tools/cloudbeaver/preflight.py --context "$CB_CONTEXT" --kubeconfig "$CB_KUBECONFIG"
```

If an operator already has an approved application session, the optional `--session-cookie-file /restricted/path/session.cookies` reads a Netscape cookie file. It makes only supported inventory queries over HTTPS, with no authentication attempt or SQL. It rejects anonymous sessions, including the object returned during setup, and requires an enabled persistent account matching the authenticated identity. It reports counts and an inventory hash, not usernames, connection names or credentials. Protect the cookie and report outside Git. Session/query handling can create normal application session or audit activity; it makes no account/configuration changes.

Before deciding a recovery branch, record and review:

1. Actual Argo CD applied and desired revisions, pending operations, root and child automation, resource diff, Deployment history, image IDs/digests, Pod restart history, events and selected current/previous startup evidence. A tag does not establish the deployed bytes. Avoid unfiltered logs, environment dumps and Secret YAML.
2. ExternalSecret Ready condition, Secret key presence, normalized administrator identifier checks and Pod snapshot versus current Secret. Never display/decode passwords. The bootstrap identifier need not identify an existing account. Separately establish the approved existing administrator credential source for `CB_VERIFY_*`; do not test guessed passwords repeatedly.
3. PVC/PV name and UID, Bound status, claim reference, reclaim policy, local-path node affinity, actual mount, free space, metadata and ownership. Preserve UID/GID 8978 data access and the image's root launcher behavior. Check the live PVC protection annotations, not only Git. Do not read live H2 contents.
4. Presence/size of `.data/cb.h2v2.dat.mv.db`, `.data/.database-credentials.dat` and `.data/.cloudbeaver.runtime.conf`; parse only selected non-sensitive runtime fields. A nonempty `server.serverName`, a marker or an open H2 connection is insufficient evidence of completed installation. Inspect trusted same-installation runtime backups without printing their contents.
5. Persistent users, including disabled users, teams, grants, settings, projects and connection inventory through approved authenticated APIs. GlobalConfiguration alone does not inventory every user's project. Preserve a restricted full comparison inventory through supported APIs on the clone. A visible `admin` subject can be a built-in team. If no safe authenticated inventory is available, defer inspection to a cold backup clone; do not open running H2 or rerun setup to inspect it.

CloudBeaver 26.2.2 rejects `listUsers`/`listTeams` in configuration mode. Do not fabricate runtime settings or complete setup to unlock inventory. If supported authenticated inspection cannot establish the prerequisites, remain in D and obtain separate approval for a safe inspection method on an isolated cold-backup copy. The synthetic C regression uses a known newly created volume and its complete failed-bootstrap history; it does not establish how to audit an arbitrary production database.

The helper reports selected evidence, not comprehensive database integrity or every project. Failures or missing optional permissions remain unknown facts. In the reviewed environment the default context list was empty; kubeconfig, Argo authentication and SSH-agent access were absent. The separate disposable kind context is not production access. No production recovery branch has been established.

## Operator evidence checklist

Complete this checklist using the approved read-only context before reviewing recovery. Keep reports outside Git, restrict their permissions and share them only through the approved private channel. A denied request, missing field, stale observation or blocked report remains unknown evidence; retain NO-GO and scenario D until it is resolved. None of these commands changes a resource or opens H2.

- [ ] Confirm the approved context and kubeconfig selectors, relevant namespace/cluster RBAC, and the intended production environment. Do not fetch credentials, escalate permissions or change contexts to work around a denial.
- [ ] Capture the sanitized helper report in a private directory. Stop and inspect `blocked`/unavailable fields before proceeding:

```bash
set -euo pipefail
: "${CB_CONTEXT:?Set the approved read-only production context}"
: "${CB_KUBECONFIG:?Set the approved kubeconfig path}"
umask 077
CB_REPORT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/cloudbeaver-preflight.XXXXXX")
python3 tools/cloudbeaver/preflight.py --context "$CB_CONTEXT" --kubeconfig "$CB_KUBECONFIG" > "$CB_REPORT_DIR/metadata.json"
```

- [ ] Record actual Pod image IDs, node/Pod identities, restart counts and mounted claim references across the entire namespace. The helper’s `workspace_consumers` includes unlabelled Jobs and pending/terminating Pods, with read-only versus writable mounts; `workspace.available` requires metadata for all three installation files and records explicit `missing|path` markers. Neither ReadWriteOnce nor the application lock excludes an unguarded same-node writer. Compare all consumers with the applied Deployment and intended claim:

```bash
kubectl --kubeconfig "$CB_KUBECONFIG" --context "$CB_CONTEXT" get pods -n medilab \
  -o 'custom-columns=NAME:.metadata.name,UID:.metadata.uid,NODE:.spec.nodeName,PHASE:.status.phase,RESTARTS:.status.containerStatuses[*].restartCount,IMAGES:.status.containerStatuses[*].imageID,CLAIMS:.spec.volumes[*].persistentVolumeClaim.claimName' \
  > "$CB_REPORT_DIR/pods.txt"
kubectl --kubeconfig "$CB_KUBECONFIG" --context "$CB_CONTEXT" get pvc cloudbeaver-workspace -n medilab \
  -o 'custom-columns=NAME:.metadata.name,UID:.metadata.uid,PV:.spec.volumeName,PHASE:.status.phase,CLASS:.spec.storageClassName,CAPACITY:.status.capacity.storage' \
  > "$CB_REPORT_DIR/claim.txt"
CB_PV=$(kubectl --kubeconfig "$CB_KUBECONFIG" --context "$CB_CONTEXT" get pvc cloudbeaver-workspace -n medilab -o jsonpath='{.spec.volumeName}')
: "${CB_PV:?Claim is not bound; stop recovery assessment}"
kubectl --kubeconfig "$CB_KUBECONFIG" --context "$CB_CONTEXT" get pv "$CB_PV" \
  -o 'custom-columns=NAME:.metadata.name,UID:.metadata.uid,CLAIM_UID:.spec.claimRef.uid,RECLAIM:.spec.persistentVolumeReclaimPolicy,NODE_AFFINITY:.spec.nodeAffinity,LOCAL_PATH:.spec.local.path,HOST_PATH:.spec.hostPath.path' \
  > "$CB_REPORT_DIR/volume.txt"
CB_STORAGE_CLASS=$(kubectl --kubeconfig "$CB_KUBECONFIG" --context "$CB_CONTEXT" get pvc cloudbeaver-workspace -n medilab -o jsonpath='{.spec.storageClassName}')
test -n "$CB_STORAGE_CLASS" || { printf '%s\n' 'StorageClass is missing; stop recovery assessment' >&2; exit 1; }
kubectl --kubeconfig "$CB_KUBECONFIG" --context "$CB_CONTEXT" get storageclass "$CB_STORAGE_CLASS" \
  -o 'custom-columns=NAME:.metadata.name,PROVISIONER:.provisioner,BINDING:.volumeBindingMode,RECLAIM:.reclaimPolicy' \
  > "$CB_REPORT_DIR/storageclass.txt"
```

- [ ] Inventory dormant controllers that can create another workspace consumer. Inspect owner references and the actual controller/bootstrap responsible for each Pod, including custom controllers or hooks installed in this cluster. Before any later approved cold backup, establish that every writer has stopped and no controller can recreate one; a Pod-only inventory is a point-in-time observation. These commands do not suspend anything:

```bash
kubectl --kubeconfig "$CB_KUBECONFIG" --context "$CB_CONTEXT" get jobs -n medilab \
  -o 'custom-columns=NAME:.metadata.name,ACTIVE:.status.active,CLAIMS:.spec.template.spec.volumes[*].persistentVolumeClaim.claimName' \
  > "$CB_REPORT_DIR/jobs.txt"
kubectl --kubeconfig "$CB_KUBECONFIG" --context "$CB_CONTEXT" get cronjobs -n medilab \
  -o 'custom-columns=NAME:.metadata.name,SUSPENDED:.spec.suspend,CLAIMS:.spec.jobTemplate.spec.template.spec.volumes[*].persistentVolumeClaim.claimName' \
  > "$CB_REPORT_DIR/cronjobs.txt"
kubectl --kubeconfig "$CB_KUBECONFIG" --context "$CB_CONTEXT" get deployments,statefulsets,daemonsets,replicasets -n medilab \
  -o 'custom-columns=KIND:.kind,NAME:.metadata.name,REPLICAS:.spec.replicas,CLAIMS:.spec.template.spec.volumes[*].persistentVolumeClaim.claimName' \
  > "$CB_REPORT_DIR/workload-controllers.txt"
```

- [ ] Check Argo's desired/applied revisions, live auto-sync/prune/self-heal and any pending operation. Confirm which Application or bootstrap mechanism owns the child before proposing a hold. The repository declares `main`; publishing a feature branch is not evidence that live Argo configuration matches Git. Inspect the child without printing repository credentials:

```bash
kubectl --kubeconfig "$CB_KUBECONFIG" --context "$CB_CONTEXT" get application.argoproj.io cloudbeaver -n argocd \
  -o 'jsonpath={.spec.source.targetRevision}{"\n"}{.status.sync.revision}{"\n"}{.status.sync.status}{"\n"}{.status.health.status}{"\n"}{.spec.syncPolicy.automated}{"\n"}{.status.operationState.phase}{"\n"}' \
  > "$CB_REPORT_DIR/argocd.txt"
kubectl --kubeconfig "$CB_KUBECONFIG" --context "$CB_CONTEXT" get application.argoproj.io cloudbeaver -n argocd \
  -o 'jsonpath={.metadata.ownerReferences}{"\n"}{.metadata.labels.argocd\.argoproj\.io/instance}{"\n"}{.metadata.annotations.argocd\.argoproj\.io/tracking-id}{"\n"}{.metadata.managedFields[*].manager}{"\n"}' \
  > "$CB_REPORT_DIR/application-owner.txt"
kubectl --kubeconfig "$CB_KUBECONFIG" --context "$CB_CONTEXT" get applications.argoproj.io -n argocd \
  -o 'custom-columns=NAME:.metadata.name,REVISION:.spec.source.targetRevision,PATH:.spec.source.path,MULTISOURCE_PATHS:.spec.sources[*].path,AUTOMATED:.spec.syncPolicy.automated' \
  > "$CB_REPORT_DIR/applications.txt"
```

- [ ] Confirm ExternalSecret Ready/key presence, safe identifier checks and proven current verifier credential source. Never dump the Secret or try guessed passwords. If an existing approved session is available, rerun the helper with `--session-cookie-file "$CB_SESSION_COOKIE_FILE"`; keep that file private and do not create a production session solely for this checklist without approval.
- [ ] Establish actual mount/ownership/free space. Select the already running application Pod from `pods.txt`; do not create a diagnostic Pod or restart a workload to make inspection possible. If no application container is running or `exec` is forbidden, retain the evidence gap:

```bash
: "${CB_POD:?Set the inspected running CloudBeaver Pod from pods.txt}"
kubectl --kubeconfig "$CB_KUBECONFIG" --context "$CB_CONTEXT" exec -n medilab "$CB_POD" -c cloudbeaver -- \
  df -Pk /opt/cloudbeaver/workspace > "$CB_REPORT_DIR/free-space.txt"
kubectl --kubeconfig "$CB_KUBECONFIG" --context "$CB_CONTEXT" exec -n medilab "$CB_POD" -c cloudbeaver -- \
  stat -c '%n|%u|%g|%a' /opt/cloudbeaver/workspace /opt/cloudbeaver/workspace/.data > "$CB_REPORT_DIR/ownership.txt"
```

- [ ] Establish runtime presence/provenance, startup-error evidence and full account/project/connection inventory through approved safe methods. The helper reports selected metadata and GlobalConfiguration only. Configuration mode blocks administrative inventory APIs; unavailable evidence cannot authorize C.
- [ ] Submit the complete sanitized evidence, chosen A/B/C/D branch, exact proposed hold/repair/rollout revisions, credential-reference decisions, cold-backup destination, restore rehearsal, acceptance criteria and rollback triggers for owner/operator review. Leave all production changes pending explicit approval.

## Approval and consistent backup

Submit the production evidence, chosen A/B/C/D branch, exact proposed Git revisions/manifests, credential-reference checks, downtime, backup destination, restore test, rollback triggers and named operators for review. No recovery-changing command is authorized by this document. The normal Kustomization intentionally contains no recovery Job.

After approval and the Git reconciliation hold below, stop the sole writer cleanly. Take an encrypted **cold backup of the entire workspace**, including dotfiles, `.data`, encryption material, `.metadata`, GlobalConfiguration, all user projects, connection JSON and credential files. Use a reviewed backup Job mounting the original PVC read-only and writing to an approved encrypted destination outside both the PVC and its node. Preserve numeric ownership/modes and record checksums, image digest, Git revision and PV/PVC identities in a restricted manifest. A live file copy or database snapshot without demonstrated consistency does not replace this backup.

Restore the immutable archive into a different isolated volume with no public ingress and no route to production databases. Use the exact deployed image. Verify archive integrity, modes, original administrator login, all users/teams/grants, settings, project inventory and saved credentials. Test connections against synthetic endpoints; actual production database access needs separate authorization. Record the restore duration, encryption-key custody and retrieval procedure, destination immutability and retention before approving the backup method. Never mount the original production PVC into the clone. Clone startup can write its own H2 through the supported application; never directly edit production H2. No verified cold backup and restore test means no repair.

## Recovery decision tree

An attempt marker without completed runtime settings goes through this tree; removing the marker is never a recovery action. A changed Secret identifier alone does not select C. Upstream automatic setup can reset an existing user's supplied password and memberships.

| Scenario | Preconditions | Safest reviewed action | Backup requirements | Exact validation | Rollback | Immediate stop |
| --- | --- | --- | --- | --- | --- | --- |
| **A. Runtime exists and is valid** | Expected PVC/H2 and key material; trusted runtime; supported API proves existing accounts and usable original administrator; clone matches inventory | Deploy guard without setup. Remove bootstrap variables from application launch. Point verifier references at the proven existing credential source; keep account/password unchanged | Full cold archive and successful isolated restore; retain runtime and inventory | Original password works; expected accounts/grants/projects/settings/connections match; configuration mode false; authenticated readiness, Service and route work; same PVC UID through approved restarts | Hold reconciliation, scale to zero through approved Git revision; revert affected configuration while retaining guard/protection; preserve current data | Wrong PVC/digest, unreadable runtime, absent/empty H2, account/credential mismatch, duplicate users or unreadable saved connections |
| **B. Runtime missing but prior initialization proven** | Historical completion or persistent users/settings demonstrated on clone; expected H2/key material; verified completed runtime backup from this same installation | Restore only trusted runtime settings through a separately reviewed repair Job while stopped. Never run setup or fabricate a server name | Full cold archive; preserve pre-repair runtime state; restore-test file-only repair on isolated volume | H2 checksum unchanged across stopped file-only repair; original login and full inventory match; all A acceptance criteria after launch | Stop writer; restore pre-repair runtime state only, preserving both versions and unchanged H2; missing-runtime state remains safely blocked | No trusted runtime backup/settings, uncertain origin, any H2/key change during repair, original login fails; return to D/owner review |
| **C. Genuinely incomplete initialization** | Corroborated first-installation history establishes setup never completed; isolated clone shows no users, including disabled users, and only default teams; exact shipped initial-data configuration verified; no custom initial administrator. Unknown history is D | Review a non-team identifier, its approved configuration/Secret references and matching verifier references; preserve the intended bootstrap password. Any production identifier/provider change needs explicit approval. On clone prove one supported auto-configuration attempt completes. Separately approve a single recovery Job outside normal Kustomization, `backoffLimit: 0`, one writer, same image/PVC and a finite reviewed deadline. Stop it cleanly after runtime completion, then resume guarded Deployment | Full cold archive and inspected clone before the attempt; preserve failed-attempt evidence | Exactly the approved new account and existing default teams; password/roles as approved; runtime persists; no subsequent setup/security creation; all A lifecycle/readiness/connection checks | Stop writer and preserve failure state; normal guard blocks retry. Code rollback does not undo created data; any full workspace restoration requires separate approval | Any existing user, unknown account state, prior completion evidence, custom initial-data behavior, unexpected account or credential change, timeout or second attempt |
| **D. Data/integrity uncertain** | Missing safe account evidence, unexpected storage identity, absent H2/key material, corrupt files, unexplained history, untrusted backup or failed restore | Fail closed. Preserve claim and evidence; obtain authorized diagnosis and cold backup/clone. Escalate storage/runtime restoration decision; no setup and no automatic repair | Immutable whole-workspace archive plus storage metadata; verify consistency and restoration before selecting another branch | Resolve identity/integrity and inventory unknowns using supported application APIs on isolated copies; only then reclassify as A/B/C | Keep writer stopped and original data retained; no implicit H2 replacement, downgrade or claim recreation | Any operation would overwrite uncertain data, require live H2 access, lose key material, lack a restorable backup or exceed reviewed authorization |

No branch authorizes deleting a user/team, resetting H2, completing the public wizard, rotating production Secrets or replacing the PVC. If C's prerequisites cannot be proved without unsafe inspection, choose D.

## Proposed GitOps rollout sequence

`infra/cluster/applications/cloudbeaver.yaml` watches `main` with auto-sync, prune and self-heal. Identify the live owner before relying on parent reconciliation: the Argo role default disables the root Application, while the checked-in production inventory enables it. Neither repository setting proves which root or child Application currently owns the live resource. A parent may reconcile the child, but repository templates do not establish live ownership. **Merging the candidate to `main` is already a production deployment trigger.** A later promise to manually sync does not provide a gate.

After explicit authorization, use separate reviewed revisions in this order:

1. From the verified production Git state, prepare a **hold revision containing only removal of `spec.syncPolicy.automated` from the CloudBeaver child Application** in `infra/cluster/applications/cloudbeaver.yaml`. Have the verified declarative owner apply this Git state: parent reconciliation only if that parent actually manages this child; otherwise a separately reviewed bootstrap/adoption path. If no verified owner can deliver the hold, stop and review ownership before any candidate merge. Do not enable the optional root Application as an implicit recovery step. Confirm the live child has automation disabled and no running or queued sync/retry. Check installed Argo semantics and parent differences. Do not merge the candidate yet. Do not rely on a live UI toggle that parent self-heal can reverse.
2. Prepare a holding application revision with the existing workload configuration, `replicas: 0` and PVC `Prune=false,Delete=false`. Review the complete diff against the actual applied revision. Through an approved manual sync, protect the **existing** claim and stop the writer. Confirm live protection, same PVC/PV UID, no app/backup/legacy writer and no usable public backend. No force, replace, namespace pruning, Secret changes or unrelated drift is permitted.
3. Run the separately reviewed backup Job and restore test described above. Select A/B/C/D from actual evidence. Approve exact repair manifests only for B or C after clone proof; D does not proceed. Recovery Jobs remain outside `infra/cluster/cloudbeaver/kustomization.yaml`, without an automatic retry/sync hook.
4. With child automation still held, approve the final candidate revision and complete diff. Keep the existing claim, storage class, capacity, mount, single replica/Recreate strategy and CloudBeaver 26.2.2. Compare production image digest with the tested digest; hold if different until validated. The JDBC change must target the **same** embedded path and existing management credential file with `WRITE_DELAY=0`, not a replacement database or supplied DB user/password. Verify `CB_VERIFY_*` Secret references against original login on the clone; do not reset the account. Confirm generated ConfigMap hash and Service readiness behavior. Candidate application manifests remain at zero replicas until any approved recovery completes.
5. Apply the separately approved B/C action, if needed, with the application still stopped. Verify its stop criteria, save before/after evidence, and ensure the recovery writer has terminated. Approve and synchronize the final Git revision restoring only the guarded Deployment to one replica. Monitor initial startup and authenticated readiness. A failed verifier stays unavailable rather than changing an account; diagnose its source/latch before approving any restart.
6. Validate all acceptance criteria below. Keep automation held if any fail. Only after acceptance, approve a Git revision restoring the child's normal auto-sync/prune/self-heal and reconcile it through the same verified declarative owner. Confirm live policy, synchronization, health and PVC protection. Retain backups and review evidence. Close #286 only after production acceptance is recorded.

These are proposed operations, not executed recovery. Exact holding/repair commit IDs and Job parameters require the unavailable production evidence and approval. Do not reuse an old unconditional connection writer as a holding or rollback workload.

## Production acceptance criteria

1. Actual image digest/version and same PV/PVC identities match the reviewed plan; ExternalSecrets are Ready, relevant key references exist and expected ownership/mount/free space are established.
2. Persisted runtime and H2 exist, GraphQL boolean `configurationMode=false`, the original administrator authenticates with the original password, and protected account/connection queries succeed. Full user/team/grant/project/settings/connection inventories match the backup. Existing saved connections remain accessible without credential overwrite. The readiness probe does not prove remote database availability; validate authorized connections separately.
3. EndpointSlices publish only Ready backends. Service and public route provide the normal application. Setup-mode, accountless and wrong-verifier clones have no usable Service/IngressRoute backend. RBAC and network controls restrict direct Pod access; readiness alone is not network isolation.
4. Separately approved restarts and Pod recreation retain the same PVC UID, original login, accounts, settings, connection credentials and nonconfiguration mode. No duplicate accounts, setup/security completion or collision errors appear. Prove abrupt-startup recovery and crash durability on the isolated clone; production fault injection is not implied.
5. Probe duration/error rates and storage I/O show no new timeout or durability errors under the reviewed workload; the synchronous H2 setting and repeated Java probes require production-like storage/resource validation on the clone.
6. Argo CD is healthy and synchronized at the approved revision with the reviewed final automation. The live claim carries both protection options; no force/replace or namespace-deletion path is introduced. Backup restoration remains reproducible.

## Rollback and recovery

Trigger rollback for failed readiness, wrong image/storage identity, original-login failure, changed inventory, inaccessible saved credentials, repeated setup or unreviewed mutations. Keep the public backend unavailable and stop the writer using the approved Git hold/zero-replica sequence. Preserve the current workspace for diagnosis.

Revert only affected code/configuration while retaining the startup guard, PVC protection and reconciliation hold. Do not blindly revert to an old connections writer, run an Argo CD live Rollback, retry setup, downgrade CloudBeaver against unknown H2 state or remove the claim. The H2 write-delay setting is persistent; a code revert is not a data rollback.

For B's file-only repair, restore the saved pre-repair runtime state while stopped and verify H2 remains unchanged. For any startup that changed persistent data, Git cannot reverse those writes. Validate the immutable archive on another volume and obtain separate approval for any production workspace restoration, including the resulting loss of later changes. This procedure grants no permission to replace production H2.

## Related documents

- [Security and peer review](../reports/cloudbeaver-security-review.md)
- [Cluster](../infrastructure/cluster.md#cloudbeaver)
- [Secrets](../infrastructure/secrets.md)
- [CloudBeaver review](../reports/cloudbeaver-review.md)
- [Initialization evidence and older implementation comparison](../reports/cloudbeaver-initialization.md)
- [Provisioning a node](provisioning-node.md)
