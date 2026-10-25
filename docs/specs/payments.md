# Payments and reconciliation

Stories: US-A06, US-A07, US-A08, US-A09, US-A10, US-A13

## Goal

Money received against an invoice is an Odoo payment. Sales can record cash and bank transfers as drafts. The accountant confirms them, which reconciles the invoice, or rejects them. PayOS payments are posted from the confirmed transaction. Each Vietnam day of PayOS transactions can be locked.

## Design

- `account.payment.method` is `online`, `bank_transfer` or `cash`. `reviewed_by_id`, `reviewed_at` and `rejection_reason` record the accountant's decision.
- A draft does not change the invoice's `payment_state`. Confirming posts the payment and reconciles it with the invoice, so the status stays Odoo's: not paid, partial, in payment or paid.
- Cash and bank transfers cannot be more than the invoice residual. The invoice row is locked before that check. Two payments that would together pass the residual fail when the second is confirmed.
- Rejecting a draft cancels it, leaves the invoice as it was, creates an activity for the salesperson with the reason, and queues `payment.rejected` for the customer.
- Confirming a payment queues `payment.receipt` for the customer. Neither notice is sent inside the payment transaction: the mail job sends it afterwards, and a failure there does not undo the payment.
- The receipt is Odoo's payment receipt. Its number is the payment journal sequence, assigned when the payment is posted. A customer opens only a receipt of their own invoice.
- The invoice PDF shows VietQR through Odoo's invoice report and the Vietnamese localisation. This module does not draw a QR code. A manual bank transfer stays a draft until the accountant confirms it.
- A PayOS payment is posted for the amount of that bank transfer. When that amount is more than the residual, `exceeds_residual` is set and the extra money stays on the payment. The invoice does not get a second debt status. A smaller transfer is a partial payment. The portal shows PayOS and bank transfer. PayOS starts a checkout transaction. Bank transfer creates one draft, and a second submit returns that draft. The draft is not confirmed by the customer. The return page does not confirm PayOS.
- The invoice page posts to `/my/invoices/<id>/pay` with the CSRF token and an amount. The server rounds that amount to the invoice currency, refuses zero or less, and refuses more than the residual. An empty amount means the residual. A draft bank transfer or an open PayOS link is reused; its stored amount is not replaced. The PayOS link is created for the accepted amount. The PayOS webhook does not use that token, and it checks the signature instead. Portal users cannot read `payment.provider` or `payment.method`. The invoice page only learns whether PayOS is published. Opening `/my/invoices/<id>` is the account portal route: a posted invoice of that customer, or a valid access token for that invoice. A draft, another customer, or a wrong token goes back to the portal home. The PDF download uses the same check.
- A reconciliation day lists PayOS transfers whose `payos_transferred_at` falls on that calendar day in Asia/Ho_Chi_Minh. It does not use the moment the row was created. Post missing payments creates the payment for a confirmed transfer that has none. The day cannot be locked while a payment is missing, or while an overpayment or an amount difference is not acknowledged. Locking freezes online payments of that transfer day. There is no unlock. A confirmation for a locked day is still stored and marked `recorded_after_lock`. A transfer for another day is not marked late because this day is locked. Printing the day lists each bank reference, transfer, payment, invoice, missing payment, overpayment and late transfer, and the transfer, payment and difference totals. An empty day prints zeros.
- `sale.order.pending_amount` is the sum of draft cash and bank-transfer payments on the order's invoices. Confirming or rejecting a payment removes it from that sum. It does not change `payment_status`.
- A new cash, bank or PayOS amount above the residual is refused. A PayOS webhook for money already transferred is still recorded, and `exceeds_residual` flags the extra. It is not refunded.
- `overdue.reminders` queues one `invoice.overdue` message per overdue invoice per Vietnam date. Running it again the same day does not send a second one.
- Confirming and rejecting need the accountant billing group or an administrator. `account.payment` does not use the permission mixin, because Odoo writes it while posting and reconciling. The reconciliation day is a new model, so it uses the mixin and ships read, create and edit permissions.

Paying the advance invoice of a quotation accepts that quotation. `sale.order.payment_status` is not paid, partially paid or paid from the posted customer invoices; a draft payment does not change it. A customer allowed to order on credit is `medilab.customer.sales.terms.allow_credit`, and confirming their unpaid test request is allowed. A customer without that flag cannot confirm the request until the order is paid.

## Related documents

- [Accountant](../functional/ecommerce_module/features/accountant.md)
- [Invoices](invoices.md)
- [PayOS](payos.md)
- [E-commerce diagram](../infrastructure/database/ecommerce/ecommerce.prisma)
