# Shared questions

- **Certificate holder.** Whose certificate signs the printed documents: one laboratory certificate for all documents, or a certificate per signer or role (for example the Head of Sales for quotations)? This decides how many certificates Viettel Sign must hold. (blocks SH-04)
- **SMS.** The customer notification preferences include SMS. Brevo can be used for it, or another provider. (blocks US-C07)
- **Lock timeout.** The inactivity period after which an editing lock is released. (blocks SH-06)
- **Archived kinds.** Besides audit entries, which records does the cleanup job archive before removing them: job runs, notifications, locks, devices? (blocks SH-09)
- **OCA modules.** OCA `queue_job` (job queue) and `auditlog` (audit log) have Odoo 20 migrations under review ([OCA/queue#999](https://github.com/OCA/queue/pull/999), [OCA/server-tools#3771](https://github.com/OCA/server-tools/pull/3771)); `base_tier_validation` (approval tiers) is released only up to Odoo 18. Until they are released, scheduled jobs, the audit trail and approval chains are built on Odoo Community alone. Once they are, should MediLab move onto them? (blocks SH-05, SH-09, US-AD14)
- **Notification choices.** Odoo lets each user receive all messages either in the application or by e-mail. The documents let a person turn each channel on or off per event, which MediLab keeps on top of Odoo. Is Odoo's single choice enough, or is the per-event choice needed? (blocks SH-11, US-C07)

## Related documents

- [Shared technical features](../docs/functional/shared.md)
