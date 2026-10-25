# Payments and reconciliation

Stories: US-A06, US-A07, US-A08, US-A09, US-A10, US-A13

## Goal

Record money received for an order's advance request or posted invoice without confusing receipt with revenue or customer agreement. Sales records cash and transfers as pending; the accountant verifies or rejects them. Verified PayOS transactions establish receipt. An advance remains linked to its order before there is an invoice. Each Vietnam day of PayOS transactions can be locked.

## Design

### Advance receipts and allocation

- Advance payment requests and acceptance follow [Payment requests](payment-requests.md). No invoice is required to record an advance. Verification records the customer's advance and a receipt for the actual amount, independently of service revenue.
- Preserve the original request, quotation version, provider link and actual transfer time alongside verification and allocation history. Money from a prior quotation stays on the same order.
- A verified transfer found through an obsolete link is recorded once and awaits accountant review before it is allocated to a replacement request. Display such retained receipts separately so Sales does not request the same money again.
- A new payment action is limited to the current target's remaining amount. If PayOS reports an actual transfer above that amount, record it in full and flag the excess; neither expiry nor a provider cancellation can erase an actual receipt.
- Reach the advance threshold using verified receipts applied to the current version. An order with an advance requirement cannot start collection or testing before full funding, customer acceptance and order approval, regardless of credit permission.

### Invoice payments and reconciliation

- `account.payment.method` is `online`, `bank_transfer` or `cash`. `reviewed_by_id`, `reviewed_at` and `rejection_reason` record the accountant's decision.
- A draft does not change the invoice's `payment_state`. Confirming posts the payment and reconciles it with the invoice, so the status stays Odoo's: not paid, partial, in payment or paid.
- Cash and bank transfers cannot be more than the invoice residual. The invoice row is locked before that check. Two payments that would together pass the residual fail when the second is confirmed.
- Rejecting a draft cancels it, leaves the invoice as it was, creates an activity for the salesperson with the reason, and queues `payment.rejected` for the customer.
- Confirming a payment queues `payment.receipt` for the customer. Neither notice is sent inside the payment transaction: the mail job sends it afterwards, and a failure there does not undo the payment.
- The receipt is Odoo's payment receipt. Its number is the payment journal sequence, assigned when the payment is posted. A customer opens only a receipt belonging to their own order or invoice.
- The invoice PDF shows VietQR through Odoo's invoice report and the Vietnamese localisation. This module does not draw a QR code. A manual bank transfer stays a draft until the accountant confirms it.
- A PayOS payment is posted for the amount of that bank transfer. When that amount is more than the residual, `exceeds_residual` is set and the extra money stays on the payment. The invoice does not get a second debt status. A smaller transfer is a partial payment. The portal shows PayOS and bank transfer. PayOS starts a checkout transaction. Bank transfer creates one draft, and a second submit returns that draft. The draft is not confirmed by the customer. The return page does not confirm PayOS.
- A raising-adjustment invoice is paid separately against its own residual. The original invoice page shows only its own payable balance; order and customer debt summaries include all outstanding invoices. A manual refund of an excess advance follows the [invoice rules](invoices.md) and is linked to its order and original payment.
- The invoice page posts to `/my/invoices/<id>/pay` with the CSRF token and an amount. The server rounds that amount to the invoice currency, refuses zero or less, and refuses more than the residual. An empty amount means the residual. A draft bank transfer or an open PayOS link is reused; its stored amount is not replaced. The PayOS link is created for the accepted amount. The PayOS webhook does not use that token, and it checks the signature instead. Portal users cannot read `payment.provider` or `payment.method`. The invoice page only learns whether PayOS is published. Opening `/my/invoices/<id>` is the account portal route: a posted invoice of that customer, or a valid access token for that invoice. A draft, another customer, or a wrong token goes back to the portal home. The PDF download uses the same check.
- A reconciliation day lists PayOS transfers whose `payos_transferred_at` falls on that calendar day in Asia/Ho_Chi_Minh. It does not use the moment the row was created. Post missing payments creates the payment for a confirmed transfer that has none. The day cannot be locked while a payment is missing, or while an overpayment or an amount difference is not acknowledged. Locking freezes online payments of that transfer day. There is no unlock. A confirmation for a locked day is still stored and marked `recorded_after_lock`. A transfer for another day is not marked late because this day is locked. Printing the day lists each bank reference, transfer, payment, original advance request or invoice, missing payment, overpayment and late transfer, and the transfer, payment and difference totals. An empty day prints zeros.
- The order's pending amount includes reported cash and bank-transfer receipts for its advance requests and invoices. Verification or rejection removes that record from the pending sum; a pending receipt never counts as verified funding. Keep unapplied verified money separate from pending verification.
- A new cash, bank or PayOS amount above the residual is refused. A PayOS webhook for money already transferred is still recorded, and `exceeds_residual` flags the extra. It is not refunded.
- `overdue.reminders` queues one `invoice.overdue` message per overdue invoice per Vietnam date. Running it again the same day does not send a second one.
- Confirming and rejecting need the accountant billing group or an administrator. `account.payment` does not use the permission mixin, because Odoo writes it while posting and reconciling. The reconciliation day is a new model, so it uses the mixin and ships read, create and edit permissions.

An order shows verified money received, money awaiting verification or allocation, the remaining advance requirement and its uncollected total separately. Reaching the advance threshold is not the same as paying the whole order. Posted invoices keep their own payment status; an unposted request does not manufacture invoice debt.

## Related documents

- [Accountant](../functional/ecommerce_module/features/accountant.md)
- [Invoices](invoices.md)
- [Payment requests](payment-requests.md)
- [PayOS](payos.md)
- [E-commerce diagram](../infrastructure/database/ecommerce/ecommerce.prisma)
