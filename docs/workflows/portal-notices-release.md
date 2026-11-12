# Releasing and rolling back portal notices

How to deploy the release that adds `portal_visible` and `portal_seen_at` to `mail.notification` (`sol_laboratory` 20.0.1.36.0) so that no mandatory notice or first-open time is lost, and how to roll it back and forward. The portal behaviour is in [Shared requirements](../functional/shared.md) (SH-11) and [Customer features](../functional/ecommerce_module/features/customer.md); the rollout is in [Cluster](../infrastructure/cluster.md).

## What the release leaves in the database

| Item                                 | Meaning                                                                                                                               |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- |
| `mail_notification.portal_visible`   | The notice is shown in the recipient's portal. Empty on every row written before the release or by code that does not know the column |
| `mail_notification.portal_seen_at`   | The first time the recipient opened the notice in the portal                                                                          |
| `sol_laboratory.notice_portal_since` | System parameter, UTC to the second, set once by the migration at the start of the upgrade and never changed by a later run           |

The portal shows a notice to its own recipient when `portal_visible` is true, when it is in the Odoo inbox, or when it is a mandatory notice, the recipient has a portal account and its message was created at or after `notice_portal_since`. The last rule is what keeps a notice written by code that does not know the columns visible. It reads the message's creation time, which Odoo sets and a caller cannot, not its date, which a caller can set to any value. A mandatory email delivered before `notice_portal_since` is not shown, and a missing or unreadable parameter shows nothing from this rule. Nobody back-fills history; an administrator who deletes the parameter turns the rule off, and one who sets it to an earlier date shows the mandatory notices written since that date.

## Who can write while the release rolls out

The upgrade job runs the new image before the Deployment rolls, so the old pod keeps serving against the upgraded schema until the new pod is ready and the old one has drained. Blue-green deployment, when it replaces the rolling update, keeps old workers for as long as the old colour serves. Measured on a database upgraded from the previous release:

| Written by                                                | Row for a recipient with a working email              | Row for a recipient with a bounced email               |
| --------------------------------------------------------- | ----------------------------------------------------- | ------------------------------------------------------ |
| Old code before the upgrade                               | Email notification, not shown (history)               | None                                                   |
| New code after the upgrade                                | `portal_visible` true, shown                          | `portal_visible` true, status `canceled`, shown        |
| Old code after the upgrade, while an old pod still serves | `portal_visible` empty, **shown** by the cutover rule | **None: the notice is not stored and cannot be shown** |
| Old image after a rollback                                | Same as the previous row                              | **None**                                               |

A read-time rule cannot show a row that was never created. The old code creates no notification for a contact whose email bounced, so a mandatory notice raised for such a contact by an old pod is lost to the portal. No audit entry records it either.

### Cutover control

A release that must lose no mandatory notice stops every old Odoo process before the upgrade job and starts only new ones: scale the Odoo Deployment to zero, let Argo CD sync the new image and its upgrade job, then scale it back up. Changing the Deployment strategy of the release to `Recreate` has the same effect. Both change how the cluster rolls out and need the owner's approval; the manifests in `infra/cluster/` do not do this today. Without the control, a mandatory notice for a bounced contact raised by an old pod during the overlap is lost, and the release record states it.

## Why a rollback needs a backup

A rollback upgrades the database with the previous image, which does not know the two columns. Odoo drops both columns and their field records, and the roll-forward creates them empty. Measured: two rows with `portal_visible` true and `portal_seen_at` set became zero and zero. First-open times cannot be recomputed, so the notices a customer already opened show as new again.

The automatic rollback in [Pipelines](../infrastructure/pipelines.md) runs the previous image's update with no pause for a backup. It runs within the verification window of a release, so what it loses is the first-open times of notices opened since the release; the cutover rule still shows the notices written meanwhile. A rollback later than that follows the sequence below.

## Rolling back

1. **Stop every writer.** Scale the Odoo Deployment to zero, so no notice is created or opened while the backup is taken.
2. **Back up** in a psql session on the primary of the database:

   ```sql
   CREATE TABLE notice_portal_backup AS
   SELECT id, mail_message_id, res_partner_id, portal_visible, portal_seen_at
   FROM mail_notification
   WHERE portal_visible IS NOT NULL OR portal_seen_at IS NOT NULL;
   ALTER TABLE notice_portal_backup ADD PRIMARY KEY (id);

   SELECT count(*) AS marked, count(*) FILTER (WHERE portal_visible) AS visible, count(portal_seen_at) AS seen,
          md5(string_agg(concat_ws(':', id, mail_message_id, res_partner_id, coalesce(portal_visible::text, '-'),
                                   coalesce(portal_seen_at::text, '-')), ',' ORDER BY id)) AS checksum
   FROM notice_portal_backup;

   SELECT count(*) AS marked_rows_missing_from_the_backup
   FROM mail_notification AS notification
   WHERE (notification.portal_visible IS NOT NULL OR notification.portal_seen_at IS NOT NULL)
     AND NOT EXISTS (SELECT 1 FROM notice_portal_backup AS backup WHERE backup.id = notification.id);
   ```

   Record the row counts and the checksum in the release record. The table holds record numbers and times, no names or addresses. It lives in the database, which an Odoo update does not touch. Also keep a file of it with `pg_dump --table notice_portal_backup` and the file's SHA-256, outside the cluster.

3. **Roll back** the image and its upgrade job. The columns are dropped; the backup table stays.
4. **Run the previous release** only as long as the rollback needs. Notices it writes have no columns; the cutover rule shows them after the roll-forward, except those for bounced contacts, which are not stored.
5. **Roll forward** with the new image and its upgrade job. The migration creates the columns, marks the inbox rows again and keeps the first `notice_portal_since`.
6. **Restore** before scaling up the new release:

   ```sql
   BEGIN;
   UPDATE mail_notification AS notification
   SET portal_visible = backup.portal_visible, portal_seen_at = backup.portal_seen_at
   FROM notice_portal_backup AS backup
   WHERE notification.id = backup.id
     AND notification.mail_message_id = backup.mail_message_id
     AND notification.res_partner_id = backup.res_partner_id;
   COMMIT;
   ```

7. **Verify** the restored state against the backup:

   ```sql
   SELECT count(*) AS rows_not_restored
   FROM notice_portal_backup AS backup
   LEFT JOIN mail_notification AS notification
     ON notification.id = backup.id
    AND notification.mail_message_id = backup.mail_message_id
    AND notification.res_partner_id = backup.res_partner_id
   WHERE notification.id IS NULL
      OR notification.portal_visible IS DISTINCT FROM backup.portal_visible
      OR notification.portal_seen_at IS DISTINCT FROM backup.portal_seen_at;

   SELECT count(*) AS marked, count(*) FILTER (WHERE notification.portal_visible) AS visible,
          count(notification.portal_seen_at) AS seen,
          md5(string_agg(concat_ws(':', notification.id, notification.mail_message_id, notification.res_partner_id,
                                   coalesce(notification.portal_visible::text, '-'),
                                   coalesce(notification.portal_seen_at::text, '-')), ',' ORDER BY notification.id)) AS checksum
   FROM mail_notification AS notification
   JOIN notice_portal_backup AS backup ON backup.id = notification.id;
   ```

   `rows_not_restored` must be 0 and the counts and checksum must equal the ones recorded in step 2. Scale the new release up. Drop `notice_portal_backup` only after the release record is closed.

## Stop conditions

Stop, leave the previous state in place and do not continue when:

- `marked_rows_missing_from_the_backup` is not 0 before step 3: a writer was not stopped, and the backup is incomplete.
- The backup's counts or checksum cannot be recorded, or the file or its SHA-256 is missing.
- `notice_portal_backup` is gone after step 3 or step 5.
- The update of step 6 changes fewer rows than the backup holds, `rows_not_restored` is not 0, or the checksum differs. A notice deleted by the cleanup job in the meantime appears here and must be explained before going on.
- The data cannot be preserved, for example the rollback must run at once with no stopped writers. Then record that first-open times are lost and the notices show as new, and have the owner accept it. Restoring the whole database from the pre-sync backup in [Cluster](../infrastructure/cluster.md) is a different decision: it discards every change since the backup.

## Limits

- A mandatory notice for a bounced contact raised by old code is never stored; only the cutover control prevents it.
- A notice written by old code has no first-open time, and the first open after the roll-forward records it.
- The cutover is read to the second, rounded down, so a notice created within the second before it is shown.
- The rule shows only portal users' own notices. An internal user, another contact of the same business and another customer are not shown them.

## Related documents

- [Shared requirements](../functional/shared.md)
- [Customer features](../functional/ecommerce_module/features/customer.md)
- [Cluster](../infrastructure/cluster.md)
- [Pipelines](../infrastructure/pipelines.md)
- [Moving a node](moving-node.md)
