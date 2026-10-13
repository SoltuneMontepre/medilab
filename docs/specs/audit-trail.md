# Audit trail

Stories: SH-05

## Goal

Every action on a document is recorded once, with who did it, when, from where, and each changed field's old and new value, without code in each feature. This spec states how entries are written, how they are protected, how a document's history is gathered and how the trail is searched and reported.

## Design

### The audit mixin

`medilab.audit.mixin` is inherited by every document model of every MediLab module, in the same way as the permission mixin, including the Odoo models MediLab extends, such as `hr.employee`, `res.partner`, `sale.order` and its lines, `payment.transaction` and `ir.attachment`. Records the trail already describes are left out: signatures, which write their own entries on the document; the items and runs of scheduled jobs and the pushes of a notification, which the job's entries describe; and messages, their notifications and their emails, which the integration entries describe. So are the Odoo models MediLab only adds behavior to: users, whose personal data their contact records and whose access comes from their person's roles; views, menus, window actions and reports, which installing a module sets; and the outgoing mail server, which comes from the environment. A test fails when any other model a MediLab module defines or extends does not inherit the mixin. The audit trail is kept apart from Odoo's field tracking, which shows changes in a document's chatter. It writes one `AuditEntry` per record for each call that changes it, in the same transaction, so an action that is rolled back leaves no entry:

| Call     | Action                                          | Changes                                                           |
| -------- | ----------------------------------------------- | ----------------------------------------------------------------- |
| `create` | `create`                                        | One `AuditChange` per stored field given a value, old value empty |
| `write`  | `edit`, or `archive` when only `active` changes | One `AuditChange` per stored field whose value changed            |
| `unlink` | `delete`                                        | None; the entry's note keeps the record's display name            |

- Only stored fields are recorded; computed fields that are not stored, binary fields and Odoo's bookkeeping fields (`create_uid`, `create_date`, `write_uid`, `write_date`, `__last_update`) are left out. A model can leave out more fields with `_audit_exclude`, such as the time a mobile device last refreshed its token.
- The fields a document keeps on another record, delegated with `_inherits` or as writable related fields, such as a job's schedule kept on its cron, are recorded as the document's own. When that record is audited itself, it records them: a person's employee details are recorded on the employee and a subcontractor's contact details on its contact, and the person's and the subcontractor's histories include them.
- A model records only some of its records when it overrides `_audit_scope`. Files are recorded only when they are attached to an audited document, such as a sample's photo; Odoo's own files, such as web assets and the stored values of image fields, are not. A file attached to a document after it was uploaded is recorded as created then. Its content is not recorded; its checksum and size show that it changed.
- A call that changes no recorded field writes no entry. A document edited together with the documents under it, such as a regulation and its limits, writes no entry for the list itself: each document under it writes its own.
- Values are written as text: a relation as the display name and id of the record, a selection as its value, a date in ISO format. A relation changes when it points to other records, not when a record it points to is renamed.
- A field marked `audit_mask=True`, such as a customer's citizen ID, records that it changed, with both values written as `***`. So do the tokens that open a document without signing in, such as an order's portal link, a mobile device's push token, the employee details Odoo shows only to HR, such as a private phone, and the credentials of a payment provider, which Odoo shows only to administrators.
- Entries are written with full rights, so a person who cannot read the audit trail still produces entries.

Other actions are written by the feature that owns them through `_audit(action, note=None)` on the mixin, on the document they act on. An action without a document, such as a webhook refused before it names one, is an entry without a document; an action on a document that is not audited names the document in its note.

| Action        | Written when                                                                                                                                                                          | Note                                   |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| `sign`        | A person signs a level of the document's chain                                                                                                                                        | The level                              |
| `approve`     | The last signature approves the document, after its `sign`                                                                                                                            | The chain                              |
| `reject`      | A person rejects the document                                                                                                                                                         | The level and the reason               |
| `withdraw`    | A person withdraws their signature                                                                                                                                                    | The level                              |
| `download`    | A person downloads a printed report or a file of the document, see below                                                                                                              | The report or the file                 |
| `job`         | A job run ends, on its scheduled job                                                                                                                                                  | The run's result and its items counted |
| `integration` | MediLab calls another system or another system calls MediLab: each call to PayOS, email sent, Firebase push, PayOS transfer and Brevo email event                                     | The system and what it did             |
| `error`       | An item fails for good, on its scheduled job, or an integration fails: an email the mail server refuses, a token Firebase rejects, a webhook refused for its token, signature or body | The item, or the system, and the error |

- A download is recorded where a printed report or a file is served: the report routes Odoo's print button uses, a PDF opened or downloaded from the portal, an invoice's documents from the portal or Odoo's Download action, a payment receipt, a quotation's stored PDF, and a file downloaded through Odoo's content routes, recorded on the file. A report shown as HTML and a file shown in the browser are pages, not downloads.
- Emails are recorded on the document of their message when Odoo's mail queue sends them, so every email through Brevo is recorded, whichever feature sent it. Brevo's events are recorded only for emails MediLab sent; an event that matches none of them is not.
- An integration entry is written in the same transaction as the work it is part of. A call whose work is rolled back, such as a job item that fails, leaves no entry; the item's error is recorded when it fails for good.

### Source and user

| Source   | When                                                                                  |
| -------- | ------------------------------------------------------------------------------------- |
| `job`    | The call runs inside a job run, and the entry links the run, or in another Odoo cron. |
| `api`    | The call comes through Odoo's external API, a route of the mobile app or a webhook.   |
| `screen` | Any other call from a signed-in user.                                                 |

The user is the signed-in Odoo user, also when Odoo acts as the superuser for them, as the portal does to read a customer's invoice; none for a webhook or a visitor who is not signed in; for a job, the user who ran it by hand, or none for a scheduled run.

### Logins and settings

Logins and logouts write an entry on the user, when Odoo writes its own login log and when the person signs out. Settings are audited by auditing writes to Odoo's system parameter table, so each changed setting records its key and its old and new value; secrets never reach that table.

### Protection

Nobody edits or deletes an audit entry or change, administrators included: the models have no `edit` or `delete` permission, and their `write` and `unlink` refuse every call. Only the cleanup job (SH-09) removes entries, through a method the job calls with its own context, once they are older than the audit retention period and written to an archive file.

### History of a document

Every audited form has a **History** button in its button box, shown to those who can read the trail, that opens the entries of the document, of the documents under it and of the files attached to them, newest first; a form without a sheet gets the button box below its header. A model names the relations of the documents under it in `_audit_children`, such as `sample_ids` on a test request, `test_ids` on a sample and `order_line` on an order, and the history follows them recursively. A deleted file still shows, found by its create entry.

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

The administrator holds it like every permission; it can be given to an auditor role. The changes of an entry are read with it.

## Related documents

- [Shared technical features](../functional/shared.md): SH-05, SH-09
- [Permissions](permissions.md)
- [Approval and signing chain](../business/approval-and-signing-chain.md)
- [Database diagram](../infrastructure/database/laboratory/laboratory.prisma)
