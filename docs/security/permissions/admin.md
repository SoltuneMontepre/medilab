# Administrator

The administrator role is an exception to permission checks: it holds every permission on every record of every module, including those that come with new features. It is Odoo's default administrator; the Odoo user created with the database holds it.

The [global rules](../readme.md#global-rules) still hold for the administrator: a signed document cannot be edited, archived or deleted, signatures, results, people who have signed a document, test parameters, parameter and method pairs and subcontractors are never deleted, and audit entries are removed only by the cleanup job after the audit retention period.

## System

- Changes settings, including the urgency threshold, the due date safety margin and the reminder lead time, scheduled job schedules and the Brevo and Viettel Sign configuration; every change is audited.
- Searches the audit trail, but cannot edit or remove an entry, and lists and downloads the archive files the cleanup job writes.
- Releases an editing lock that is stuck; this is audited.
- Runs a scheduled job by hand and retries a failed one.
- Turns digital signing on, refreshes the laboratory's certificate from Viettel Sign and receives its expiry and revocation alerts.
- Cannot change a signed document.

## Laboratory files

- Sees every computer signed in to the laboratory folders and revokes one; its person keeps their folders and other computers.
- Sees every laboratory folder with its members and sync rules, turns a folder off and on, changes its owner, who stays a member, and archives it with its retention date; an archived folder is only read, and its members can still be removed.
- Sees every laboratory file lock and releases one someone left, so others can save the file again; this is audited.
- Changes the retention period of archived folders and how long a laboratory file lock lasts in the settings.

## Onboarding

- Starts, cancels and reviews collection runs, and accepts, edits, rejects and reopens staged records.
- Refreshes the organisations of the sources by hand.
- Never sees the sources.

## Related documents

- [Security](../readme.md)
- [Laboratory administrator](../../functional/laboratory_module/features/admin.md)
- [E-commerce administrator](../../functional/ecommerce_module/features/admin.md)
- [Shared technical features](../../functional/shared.md)
