# PayOS

Stories: US-A06

## Goal

Customers pay an invoice through PayOS. The provider is Odoo's payment provider, the payment is a payment transaction, and only a signed notification from PayOS confirms it.

## Design

- The provider code is `payos`. Its client id, API key and checksum key are `PAYOS_CLIENT_ID`, `PAYOS_API_KEY` and `PAYOS_CHECKSUM_KEY`, read from the environment when a call is made. They are not stored on the provider and not written in the log. The log line is the method, the path and the order code.
- `PayosClient.request` is the only method that opens a network connection. The signature is the PayOS HMAC of the payload.
- Settings turn the provider on, turn the QR method on, and set how many hours a link lasts. The portal lists PayOS only when the provider is published and the QR method is active.
- Starting a payment creates one transaction whose reference and provider reference are the order code, and queues `payos.calls`. That job creates the link. `payos.poll` asks PayOS about links that are still open. Without the three secrets, neither job calls PayOS.
- The webhook at `/payment/payos/webhook` answers 400 when the signature does not match. The same bank reference does not create a second transaction.
- A later transfer on the same link keeps the first transaction's reference as the order code. The new transfer is another transaction: its reference is the bank reference, its provider reference is the order code, and it pays the same invoice. Odoo requires a unique transaction reference, and there is no child-transfer table.
- A payment that PayOS reports as paid after the link was cancelled or expired is still confirmed.
- `/payment/payos/return` only tells the customer that PayOS has not confirmed the payment yet. It does not post money.
- Refunds are out of this feature. Recording the `account.payment` for a confirmed transaction is the payment feature.

## Related documents

- [Accountant](../functional/ecommerce_module/features/accountant.md)
- [Scheduled jobs](scheduled-jobs.md)
- [Invoices](invoices.md)
- [E-commerce diagram](../infrastructure/database/ecommerce/ecommerce.prisma)
