# Payments and reconciliation

Stories: US-A06, US-A07, US-A08, US-A09, US-A10, US-A13

## Goal

Money received against an invoice is an Odoo payment. Sales can record cash and bank transfers as drafts. The accountant confirms them, which reconciles the invoice, or rejects them. PayOS payments are posted from the confirmed transaction. Each Vietnam day of PayOS transactions can be locked.

## Design

- `account.payment.method` is `online`, `bank_transfer` or `cash`. `reviewed_by_id`, `reviewed_at` and `rejection_reason` record the accountant's decision.
- A draft does not change the invoice's `payment_state`. Confirming posts the payment and reconciles it with the invoice, so the status stays Odoo's: not paid, partial, in payment or paid.
- Cash and bank transfers cannot be more than the invoice residual. The invoice row is locked before that check. Two payments that would together pass the residual fail when the second is confirmed.
- A PayOS payment is posted for the amount PayOS confirmed. When that amount is more than the residual, `exceeds_residual` is set on the payment. The invoice does not get a second debt status.
- Rejecting a draft cancels it, leaves the invoice as it was, and creates an activity for the salesperson with the reason.
- The receipt is Odoo's payment receipt. Its number is the payment journal sequence, assigned when the payment is posted.
- The invoice PDF shows VietQR through Odoo's invoice report and the Vietnamese localisation. This module does not draw a QR code.
- A reconciliation day lists the PayOS transactions whose creation time falls on that calendar day in Asia/Ho_Chi_Minh. Post missing payments creates the payment for a confirmed transaction that has none. Locking the day freezes online payments of that day. There is no unlock. A PayOS confirmation that arrives after the lock is stored and marked `recorded_after_lock`.
- The portal pays the signed-in customer's own posted invoice for the residual. An amount in the request is ignored. Another customer's invoice URL is refused.
- `overdue.reminders` is a scheduled job whose handler does not send a message. The channel and the mail provider come later.
- Confirming and rejecting need the accountant billing group or an administrator. `account.payment` does not use the permission mixin, because Odoo writes it while posting and reconciling. The reconciliation day is a new model, so it uses the mixin and ships read, create and edit permissions.

Paying an advance does not accept a quotation, credit customers are not modelled, and overdue reminders are not sent. Those stay open.

## Related documents

- [Accountant](../functional/ecommerce_module/features/accountant.md)
- [Invoices](invoices.md)
- [PayOS](payos.md)
- [E-commerce diagram](../infrastructure/database/ecommerce/ecommerce.prisma)
