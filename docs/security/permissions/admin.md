# Administrator

The administrator role is an exception to permission checks: it holds every permission on every record of every module, including those that come with new features. It is Odoo's default administrator; the Odoo user created with the database holds it.

The [global rules](../readme.md#global-rules) still hold for the administrator: a signed document cannot be edited, archived or deleted, signatures, results, people who have signed a document, test parameters, their parameter and method pairs and subcontractors are never deleted, and audit entries are removed only by the cleanup job after the audit retention period.

## System

- Changes settings, including the urgency threshold, the due date safety margin and the reminder lead time, scheduled job schedules and the Brevo and Viettel Sign configuration; every change is audited.
- Searches the audit trail, but cannot edit or remove an entry.
- Releases an editing lock that is stuck; this is audited.
- Runs a scheduled job by hand and retries a failed one.
- Cannot change a signed document.

## Related documents

- [Security](../readme.md)
- [Laboratory administrator](../../functional/laboratory_module/features/admin.md)
- [E-commerce administrator](../../functional/ecommerce_module/features/admin.md)
- [Shared technical features](../../functional/shared.md)
