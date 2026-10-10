# Shared questions

- **Certificate holder.** Whose certificate signs the printed documents: one laboratory certificate for all documents, or a certificate per signer or role (for example the Head of Sales for quotations)? This decides how many certificates Viettel Sign must hold. (blocks SH-04)
- **SMS.** The customer notification preferences include SMS. Brevo can be used for it, or another provider. (blocks US-C07)
- **Lock timeout.** The inactivity period after which an editing lock is released. (blocks SH-06)
- **Archived kinds.** Besides audit entries, which records does the cleanup job archive before removing them: job runs, notifications, locks, devices? (blocks SH-09)
- **Odoo app menus.** MediLab builds on Odoo apps such as Employees, Project, Calendar, Maintenance, Discuss, Sales, Invoicing, Inventory, Purchase and Manufacturing. Do people see those apps with their own menus next to the MediLab menus, or only the MediLab menus, with the apps' screens opened from them? (blocks SH-01, SH-10)
- **OCA modules.** OCA `queue_job` (job queue), `auditlog` (audit log) and `base_tier_validation` (approval tiers) have no installable Odoo 20 release yet, so scheduled jobs, the audit trail and approval chains are built on Odoo Community alone. Once they are released, should MediLab move onto them? (blocks SH-05, SH-09, US-AD14)
- **Notification choices.** Odoo lets each user receive all messages either in the application or by e-mail. The documents let a person turn each channel on or off per event, which MediLab keeps on top of Odoo. Is Odoo's single choice enough, or is the per-event choice needed? (blocks SH-11, US-C07)
- **Task assignees.** Tasks are Odoo project tasks, which are assigned to Odoo users, so a person who never signs in cannot be given a task. Is that acceptable? (blocks SH-10)

## Related documents

- [Shared technical features](../docs/functional/shared.md)
