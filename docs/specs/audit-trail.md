# Audit trail

Stories: SH-05

## Goal

Every action on a document is recorded once, with who did it, when, from where, and each changed field's old and new value, without code in each feature. This spec states how entries are written, how they are protected, how a document's history is gathered and how the trail is searched and reported.

## Design

### The audit mixin

`medilab.audit.mixin` is inherited by every document model of every MediLab module, in the same way as the permission mixin, including the Odoo models MediLab extends, such as `hr.employee` and `sale.order`. Records the trail already describes are left out: signatures, which write their own entries on the document, and the items and runs of scheduled jobs and the pushes of a notification, which the job's entries describe. The audit trail is kept apart from Odoo's field tracking, which shows changes in a document's chatter. It writes one `AuditEntry` per record for each call that changes it, in the same transaction, so an action that is rolled back leaves no entry:

| Call     | Action                                          | Changes                                                           |
| -------- | ----------------------------------------------- | ----------------------------------------------------------------- |
| `create` | `create`                                        | One `AuditChange` per stored field given a value, old value empty |
| `write`  | `edit`, or `archive` when only `active` changes | One `AuditChange` per stored field whose value changed            |
| `unlink` | `delete`                                        | None; the entry's note keeps the record's display name            |

- Only stored fields are recorded; computed fields that are not stored, binary fields and Odoo's bookkeeping fields (`create_uid`, `create_date`, `write_uid`, `write_date`, `__last_update`) are left out. A model can leave out more fields with `_audit_exclude`, such as the time a mobile device last refreshed its token.
- The fields a document delegates to another record with `_inherits`, such as a subcontractor's contact details, and its writable related fields, such as a job's schedule kept on its cron, are recorded as the document's own. When that record is audited itself, it records them: a person's employee details are recorded on the employee, and the person's history includes them.
- A call that changes no recorded field writes no entry. A document edited together with the documents under it, such as a regulation and its limits, writes no entry for the list itself: each document under it writes its own.
- Values are written as text: a relation as the display name and id of the record, a selection as its value, a date in ISO format. A relation changes when it points to other records, not when a record it points to is renamed.
- A field marked `audit_mask=True`, such as a customer's citizen ID, records that it changed, with both values written as `***`. So do the tokens that open a document without signing in, such as an order's portal link, a mobile device's push token, and the employee details Odoo shows only to HR, such as a private phone.
- Entries are written with full rights, so a person who cannot read the audit trail still produces entries.

Other actions are written by the feature that owns them through `_audit(action, note=None)` on the mixin, `download` by the controller that serves a printed document and `integration` by the integrations. The signing mixin and the scheduled jobs write theirs on the document they act on:

| Action     | Written when                                                          | Note                                    |
| ---------- | --------------------------------------------------------------------- | --------------------------------------- |
| `sign`     | A person signs a level of the document's chain                        | The level                               |
| `approve`  | The last signature approves the document, after its `sign`            | The chain                               |
| `reject`   | A person rejects the document                                         | The level and the reason                |
| `withdraw` | A person withdraws their signature                                    | The level                               |
| `job`      | A job run ends, on its scheduled job                                  | The run's result and its items counted  |
| `error`    | An item fails for good, on its scheduled job, or an integration fails | The item and the last line of its error |

### Source and user

| Source   | When                                                                                  |
| -------- | ------------------------------------------------------------------------------------- |
| `job`    | The call runs inside a job run, and the entry links the run, or in another Odoo cron. |
| `api`    | The call comes through Odoo's external API or a MediLab REST endpoint.                |
| `screen` | Any other call from a signed-in user.                                                 |

The user is the signed-in Odoo user; for a job, the user who ran it by hand, or none for a scheduled run.

### Logins and settings

Logins and logouts write an entry on the user, when Odoo writes its own login log and when the person signs out. Settings are audited by auditing writes to Odoo's system parameter table, so each changed setting records its key and its old and new value; secrets never reach that table.

### Protection

Nobody edits or deletes an audit entry or change, administrators included: the models have no `edit` or `delete` permission, and their `write` and `unlink` refuse every call. Only the cleanup job (SH-09) removes entries, through a method the job calls with its own context, once they are older than the audit retention period and written to an archive file.

### History of a document

Every audited form has a **History** button, shown to those who can read the trail, that opens the entries of the document and of the documents under it, newest first. A model names the relations of the documents under it in `_audit_children`, such as `sample_ids` on a test request and `test_ids` on a sample, and the history follows them recursively.

### Search and reports

- The **Audit Trail** app holds the trail and the report.
- An **Audit trail** screen lists entries, searched by document type, document, user, period, action and source, with the changes of each entry.
- Once a document is deleted, its entries are named, and found, by the name its delete entry keeps.
- An **Audit report** for a period, filtered the same way, prints as PDF or exports to a spreadsheet, one row per change; an entry without changes is one row.
- The retention period, in days, is set in the Laboratory block of [Settings](settings.md) and kept in the system parameter `sol_laboratory.audit_retention_days`. It is empty by default, and empty or 0 keeps entries for ever.

### Document types of this feature

| Document type | Actions | Scopes |
| ------------- | ------- | ------ |
| Audit entry   | read    | all    |

The administrator holds it like every permission; it can be given to an auditor role.

## Related documents

- [Shared technical features](../functional/shared.md): SH-05, SH-09
- [Permissions](permissions.md)
- [Approval and signing chain](../business/approval-and-signing-chain.md)
- [Database diagram](../infrastructure/database/laboratory/laboratory.prisma)
