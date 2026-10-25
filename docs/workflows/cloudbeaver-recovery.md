# CloudBeaver recovery

Use this procedure before changing an existing CloudBeaver installation. The [cluster contract](../infrastructure/cluster.md#cloudbeaver) requires preservation of the PVC, H2, accounts, settings, connections and credentials. Read-only diagnosis does not authorize recovery, Secret changes, workload restarts or Argo CD sync.

## Read-only prerequisites

Obtain an authorized Kubernetes context and access to the relevant Argo CD application. Select the context explicitly on every command; do not rely on a developer's current context. Record:

1. Argo CD's applied Git revision, desired revision and resource differences; compare the deployed image **digest**, not just its tag, with the tested image. Inspect Deployment history, Pod restart counts, events, current and previous logs. Extract only relevant startup errors; do not export unfiltered logs or environment variables.
2. ExternalSecret conditions and Secret **key names/presence**. Validate the administrator's normalized identifier against built-in team IDs without displaying it or decoding the password into terminal output. Do not change Doppler or Kubernetes Secrets during diagnosis.
3. PVC and PV UID, Bound status, reclaim policy, node affinity, capacity, mount source and mount path. Verify workspace ownership, free space and write permissions. Record filenames, sizes, permissions and modification times without printing credential files or runtime content.
4. Whether `.data/cb.h2v2.dat.mv.db` exists and whether `.data/.cloudbeaver.runtime.conf` parses and contains a nonempty string `server.serverName`. Check runtime backups, including CloudBeaver's own backup files, without assuming they represent a completed installation. Inspect only selected non-sensitive fields.
5. Existing account, team, project and connection inventory through authenticated supported APIs if available. Do not open the running H2 files. If the server is unusable, defer subject inspection to an isolated backup clone. An `admin` subject and an open H2 connection do not prove that a prior administrator exists or that setup ever completed.

The issue's reported collision is reproduced with the exact 26.2.2 image, but it is still necessary to establish the production subject type and runtime/PVC state. No configured local Kubernetes context was available for the investigation described in the [evidence report](../reports/cloudbeaver-initialization.md).

## Review and backup

Before any production-changing action, submit the observed evidence, chosen recovery branch below, proposed Git revisions/manifests, expected downtime, account/connection inventory, backup destination, restore test, rollback trigger and operator responsibilities for owner review. A read-only snapshot may assist diagnosis, but it does not replace a tested, consistent backup.

After explicit approval:

1. Prevent reconciliation from racing with recovery through a reviewed Git change that sets the CloudBeaver Deployment to `replicas: 0`. Synchronize only that reviewed change through Argo CD and wait for the sole writer to terminate cleanly. Never disable self-heal through an untracked live edit. Do not touch the PVC declaration. Keep the public backend unavailable throughout recovery.
2. Take a **cold backup of the entire workspace**, including dotfiles, `.data`, encryption material, `.metadata`, GlobalConfiguration, user projects, connection JSON and encrypted credential files. Use an approved backup Job with the existing PVC mounted read-only and an encrypted destination outside that PVC and node. The Job manifest and operation parameters belong in the reviewed recovery change; credentials belong in the approved Secret provider. Preserve numeric ownership and modes. Also record PV/PVC identity, image digest, Git revision and checksums in a restricted backup manifest.
3. Restore the archive into a **different isolated test volume**, with no production ingress and no network path to production databases. Check archive integrity and workspace checksums. Use the exact deployed CloudBeaver image. Validate recovered account counts/roles, original administrator login, settings and connection inventory. Test database login against a synthetic endpoint or obtain separate approval before connecting to a production database. Never mount the production PVC into the clone.
4. Keep the original cold archive immutable. Work only on the disposable clone to choose and prove recovery. Do not alter H2 with SQL, replace it, or delete any user/team. If no consistent backup and restore test can be obtained, stop before repair.

## Choose recovery from evidence

| Observed state | Proposed recovery after review | Stop condition |
| --- | --- | --- |
| Valid completed runtime settings and the expected H2 database | Deploy the startup/readiness guard, retaining the existing Secret and workspace. The guard removes bootstrap variables before launching. Investigate a different mounted workspace or deployed revision if the application still reports setup. | Runtime is unreadable, points to a different installation, or the expected H2 is missing or empty. |
| Previously initialized workspace; runtime missing, empty or corrupt | Restore **only verified runtime settings from the same installation's backup**, retaining the existing H2 and encryption material. Validate original administrator login, account/connection inventory and settings on the clone before restoring that file to production through a reviewed repair Job. Check H2 checksum before and after the file-only repair while CloudBeaver is stopped. | No trusted completed runtime backup or no way to establish its settings. A fabricated `serverName` is not a recovery proof. Bring the missing-settings decision back to the owner. |
| Incomplete first installation; backup clone shows only built-in teams and no prior users or completed runtime settings | Review a non-colliding initial administrator identifier and preserve the intended bootstrap password. Reproduce completion on the clone with the exact image and default initial-data configuration. A reviewed recovery Job may run CloudBeaver's supported automatic configuration once with that identifier, the existing bootstrap password and existing workspace; it must not clear H2, reset accounts, remove credential files or replace connections. Stop the Job cleanly after runtime completion before restoring the normal Deployment. Record the chosen identifier in approved configuration; do not copy any old implementation's values. | Any evidence of previous users, custom initial-data administrator configuration, unknown account state or credential changes outside the approved scope. Never run setup on a previously initialized workspace. |
| Bootstrap attempt marker exists without completed settings | It may be interrupted setup or later loss of runtime settings after successful setup; inspect the clone to choose one of the recovery branches above. The marker grants no permission to retry. | Never remove the marker merely to make the guard start. |
| Runtime settings exist but H2 is missing, or storage identity differs | Investigate storage attachment and restore availability; retain the existing PVC. | Do not initialize an empty database, replace H2, create a new claim or attach an unrelated workspace. |

The recovery Job is a proposed operation requiring a separate evidence-backed manifest and approval. It is deliberately absent from the application's normal Kustomization: self-heal must never repeatedly run recovery. Do not perform interactive public-wizard setup. Do not assume changing `CB_ADMIN_NAME` is sufficient; upstream setup can reset an existing user's credentials and team memberships.

## Roll out and validate

Use a reviewed Git revision containing the bootstrap ConfigMap, Deployment, readiness probe and PVC protection. The generated ConfigMap hash must appear in the rendered Pod template. Render with `kubectl kustomize infra/cluster/cloudbeaver` before review. Check that the Service does not publish unready endpoints and the public route still points only to that Service.

After backup and any approved recovery Job have completed, restore `replicas: 1` through the reviewed Git change and approved Argo CD sync. Keep 26.2.2, one replica, `Recreate`, and the existing `cloudbeaver-workspace` claim. Confirm:

1. The Pod becomes Ready only after runtime persistence and GraphQL `configurationMode=false`. A responding `/status` alone must not satisfy readiness. Inspect EndpointSlices and confirm unready Pods are not usable backends. With an incomplete clone, the public route must return an unavailable backend, never the wizard.
2. The original administrator can sign in with the original password. Compare all existing users, teams, grants, settings, projects and connection IDs/names with the backup inventory. Open an authorized existing connection without overwriting its saved credential. A seeded connection using obsolete `password` fields requires its own reviewed authenticated repair; provisioning intentionally leaves an existing connection untouched.
3. After separately approved application restarts and Pod recreation, the **same PVC UID** is mounted, configuration mode stays false, user counts do not increase and no security-configuration/duplicate-subject startup error occurs. Confirm the initial init container did not replace existing connections or credential files.
4. Argo CD is healthy and synchronized with self-heal/prune enabled. Confirm workspace protection remains `Prune=false,Delete=false`. Do not remove backup coverage after the rollout.

## Rollback

Rollback if readiness fails, original login fails, inventory differs or saved connections no longer work. Keep the backend unavailable while assessing it. Through the same reviewed GitOps process, set replicas to zero and retain the current workspace for investigation. Revert only the affected application configuration; do not run an old unconditional connections writer or retry setup against the original PVC. A blind revert to the faulty Deployment can damage connections and expose the wizard again.

For runtime-file-only recovery, preserve both versions and restore the pre-repair runtime file while the app is stopped; H2 must remain unchanged. If application startup changed persistent data, a Git revert does not reverse that data. Test the immutable cold backup on a separate volume and seek explicit approval for a workspace restore; this procedure does not authorize replacing production H2 or losing changes made since the backup. Do not delete/recreate the PVC, roll back the application version against an upgraded database, or use a live Argo CD Rollback as a shortcut.

## Related documents

- [Cluster](../infrastructure/cluster.md#cloudbeaver)
- [Secrets](../infrastructure/secrets.md)
- [CloudBeaver initialization evidence](../reports/cloudbeaver-initialization.md)
- [Provisioning a node](provisioning-node.md)
