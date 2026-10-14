# Audit trail

Stories: SH-05

## Goal

Every action on a document is recorded once, with who did it, when, from where, and each changed field's old and new value, without code in each feature. This spec states how entries are written, how they are protected, how a document's history is gathered and how the trail is searched and reported.

## Design

### The audit mixin

`medilab.audit.mixin` is inherited by every document model of every MediLab module, in the same way as the permission mixin, including the Odoo models MediLab extends, such as `hr.employee` and `sale.order`. The audit trail is kept apart from Odoo's field tracking, which shows changes in a document's chatter. It writes one `AuditEntry` per record for each call that changes it, in the same transaction, so an action that is rolled back leaves no entry:

| Call     | Action                                          | Changes                                                           |
| -------- | ----------------------------------------------- | ----------------------------------------------------------------- |
| `create` | `create`                                        | One `AuditChange` per stored field given a value, old value empty |
| `write`  | `edit`, or `archive` when only `active` changes | One `AuditChange` per stored field whose value changed            |
| `unlink` | `delete`                                        | None; the entry's note keeps the record's display name            |

- Only stored fields are recorded; computed fields that are not stored, binary fields and Odoo's bookkeeping fields (`create_uid`, `create_date`, `write_uid`, `write_date`, `__last_update`) are left out. A model can leave out more fields with `_audit_exclude`.
- Values are written as text: a relation as the display name and id of the record, a selection as its value, a date in ISO format.
- A field marked `audit_mask=True`, such as a customer's citizen ID, records that it changed, with both values written as `***`.
- Entries are written with full rights, so a person who cannot read the audit trail still produces entries.

Other actions are written by the feature that owns them through `_audit(action, note=None)` on the mixin: `approve`, `reject`, `sign` and `withdraw` by the signing mixin, `download` by the controller that serves a printed document, `job` and `integration` by the scheduled jobs and the integrations, and `error` where an integration or job fails.

### Source and user

| Source   | When                                                                   |
| -------- | ---------------------------------------------------------------------- |
| `job`    | The call runs inside a job run; the entry links the run.               |
| `api`    | The call comes through Odoo's external API or a MediLab REST endpoint. |
| `screen` | Any other call from a signed-in user.                                  |

The user is the signed-in Odoo user; for a job, the user who ran it by hand, or none for a scheduled run.

### Logins and settings

Logins and logouts write an entry when Odoo writes its own login log and when a session ends. Settings are audited by auditing writes to Odoo's system parameter table, so each changed setting records its key and its old and new value; secrets never reach that table.

### Protection

Nobody edits or deletes an audit entry or change, administrators included: the models have no `edit` or `delete` permission, and their `write` and `unlink` refuse every call. Only the cleanup job (SH-09) removes entries, through a method the job calls with its own context, once they are older than the audit retention period and written to an archive file.

### History of a document

Every audited form has a **History** button that opens the entries of the document and of the documents under it, newest first. A model names the relations of the documents under it in `_audit_children`, such as `sample_ids` on a test request and `test_ids` on a sample, and the history follows them recursively.

### Search and reports

- An **Audit trail** screen lists entries, searched by document type, document, user, period, action and source, with the changes of each entry.
- An **Audit report** for a period, filtered the same way, prints as PDF or exports to a spreadsheet, one row per change; an entry without changes is one row.
- The retention period is the system parameter `audit.retention_days`, empty by default, which keeps entries for ever.

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
