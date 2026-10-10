# Specs

Technical specifications of parts of the system: their design, data and behaviour.

## Writing a spec

- A feature has a spec when building it needs technical design that the functional documents do not give, such as how permissions are enforced or how the scheduler picks a slot. Features that only maintain records described by the diagram need none.
- One spec per part of the system, named after it: `<topic>.md`, such as `permissions.md`.
- A spec starts with the user story IDs it covers, then states the goal and the design. It ends with **Related documents**.

```markdown
# <Topic>

Stories: US-AD13, US-AD15

## Goal

## Design

## Related documents
```

## Specs

- [Audit trail](audit-trail.md): how actions on documents are recorded, protected, gathered into a document's history and reported
- [Invoicing](invoicing.md): how invoices are posted, numbered, frozen, corrected by adjustment invoices and printed, how payments are recorded, confirmed and receipted, and how a day's PayOS transfers are reconciled and locked
- [PayOS](payos.md): how payment links are created, verified, polled and kept in step with what PayOS reports, and how the credentials stay out of the database
- [Permissions](permissions.md): how permission, role and person records become Odoo groups and accesses, and how the own-department scope is applied
- [Scheduled jobs](scheduled-jobs.md): how jobs, their item queues and runs work: handlers, claiming, retries, running by hand and the no-overlap rule
- [Settings](settings.md): how a module declares a system parameter with its default, how features read it, who changes settings and how modules install and uninstall independently
- [Stock costing and charges](stock-costing.md): how moves are costed, stock is valued and charged to cost centres, budgets are used up and charges are exported

## Related documents

- [Documentation conventions](../conventions/documentation.md)
