# PayOS

Stories: US-A06

## Goal

Customers pay an invoice through PayOS. The provider is Odoo's payment provider, the payment is a payment transaction, and only a signed notification from PayOS confirms it.

## Design

- The provider code is `payos`. Its client id, API key and checksum key are `PAYOS_CLIENT_ID`, `PAYOS_API_KEY` and `PAYOS_CHECKSUM_KEY`, read from the environment when a call is made. They are not stored on the provider and not written in the log. The log line is the method, the path and the order code.
- `PayosClient.request` is the only method that opens a network connection. The signature is the PayOS HMAC of the payload.
- Settings turn the provider on, turn the QR method on, and set how many hours a link lasts. The portal lists PayOS only when the provider is published and the QR method is active.
- Starting a payment creates one transaction whose reference and provider reference are the order code, and queues `payos.calls`. That job creates the link. `payos.poll` asks PayOS about links that are still open. Without the three secrets, neither job calls PayOS.
- The webhook at `/payment/payos/webhook` answers 400 when the signature does not match. The signature is the HMAC of the data fields in alphabetical order, skipping keys whose value is null, compared in constant time. A code other than `00` does not record money. The browser return URL does not either.
- `amount` on a payment request is what the link asks for. Money received is `transactions[].amount` when polling, and `data.amount` on a webhook, which is that one transfer. `amountPaid` and `amountRemaining` say how much of the link is settled. Each transfer is recorded once, matched by its bank reference. A transfer without a reference is ignored, so two of them are not merged. The database rejects a second row with the same bank reference.
- The first transfer is stored on the link transaction. A later transfer on the same link is another transaction: its reference is the bank reference, its provider reference is the order code, and it pays the same invoice.
- `transactionDateTime` is Vietnam local time. It is stored in UTC as `payos_transferred_at`. Reconciliation uses that time. A transfer is `recorded_after_lock` only when the Vietnam day of that time is already locked. The payment is still posted.
- Creating a link first reads the order code from PayOS. If PayOS already has that code for the same amount, the checkout URL is reused. A timeout after PayOS created the link is retried the same way. A link for a different amount fails the item. Missing credentials leave the item queued and the log says the secrets are not set; the same item continues after they are configured.
- A payment that PayOS reports as paid after the link was cancelled or expired is still confirmed.
- `/payment/payos/return` only tells the customer that PayOS has not confirmed the payment yet. It does not post money.
- Refunds are out of this feature. Recording the `account.payment` for a confirmed transaction is the payment feature.

## Related documents

- [Accountant](../functional/ecommerce_module/features/accountant.md)
- [Scheduled jobs](scheduled-jobs.md)
- [Invoices](invoices.md)
- [E-commerce diagram](../infrastructure/database/ecommerce/ecommerce.prisma)
