# Shared questions

- **Certificate holder.** Whose certificate signs the printed documents: one laboratory certificate for all documents, or a certificate per signer or role (for example the Head of Sales for quotations)? This decides how many certificates Viettel Sign must hold. (blocks SH-04)
- **SMS.** The customer notification preferences include SMS. Brevo can be used for it, or another provider. (blocks US-C07)
- **Lock timeout.** The inactivity period after which an editing lock is released. (blocks SH-06)
- **Archived kinds.** Besides audit entries, which records does the cleanup job archive before removing them: job runs, notifications, locks, devices? (blocks SH-09)
- **Deleted parts in a history.** A document's history follows the parts it still has, so once a part is deleted, such as a sample removed from a test request, its entries no longer show in the document's history; they stay in the audit trail. Should each part's entries also name the document it belongs to, so the history keeps them? (blocks SH-05)
- **Expired sessions.** Odoo removes an expired session without telling the modules, so a logout is recorded only when the person signs out. Is a session that simply expires also to be recorded? (blocks SH-05)
- **Source of an install or upgrade.** What installing or upgrading a module writes, such as shipped permissions and their changes, is recorded with the source screen and no user. Should it have a source of its own, such as system? (blocks SH-05)
- **Masked personal data.** Besides a customer's citizen ID, which fields are personal data the audit trail masks: a person's email and phone, a customer's address, a contact's email, phone, address and tax ID, the partner email and address of a payment transaction? Until this is answered, the trail keeps their values in full. (blocks SH-05)

## Related documents

- [Shared technical features](../docs/functional/shared.md)
