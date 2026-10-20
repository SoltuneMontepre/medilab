# PayOS

Stories: US-A06

## Goal

Customers pay an invoice through PayOS. The provider is Odoo's payment provider, the payment is a payment transaction, and only a signed notification from PayOS confirms it.

## Design

- The provider code is `payos`. Its client id, API key and checksum key are `PAYOS_CLIENT_ID`, `PAYOS_API_KEY` and `PAYOS_CHECKSUM_KEY`, read from the environment when a call is made. They are not stored on the provider and not written in the log. The log line is the method, the path and the order code.
- `PayosClient.request` is the only method that opens a network connection. The signature is the PayOS HMAC of the payload.
- Settings turn the provider on, turn the QR method on, and set how many hours a link lasts. The portal lists PayOS only when the provider is published and the QR method is active.
- Starting a payment creates one transaction whose reference and provider reference are the order code, and queues `payos.calls`. A second click reuses that transaction. The portal releases the invoice lock, then claims that queued item and runs it once. The cron claims with the same pending-item rule, so the two do not both create a link. A safe `https` checkout URL is the only redirect. A link that does not match this payment, or a checkout URL that is not `https`, shows that the link is not valid. A link that is not ready yet shows a page that says the link is being prepared, with a button to try again. Neither page confirms the payment. `payos.poll` asks PayOS about links that are still open. Without the three secrets, neither job calls PayOS.
- The webhook at `/payment/payos/webhook` answers 400 when the signature does not match. The signature is the HMAC of the data fields in alphabetical order, skipping keys whose value is null, compared in constant time. A code other than `00` does not record money. The browser return URL does not either.
- `amount` on a payment request is what the link asks for. Money received is `transactions[].amount` when polling, and `data.amount` on a webhook, which is that one transfer. `amountPaid` and `amountRemaining` say how much of the link is settled. Each transfer is recorded once, matched by its bank reference. A transfer without a reference is ignored, so two of them are not merged. The database rejects a second row with the same bank reference.
- The first transfer is stored on the link transaction. A later transfer on the same link is another transaction: its reference is the bank reference, its provider reference is the order code, and it pays the same invoice.
- `transactionDateTime` is Vietnam local time. It is stored in UTC as `payos_transferred_at`. Reconciliation uses that time. A transfer is `recorded_after_lock` only when the Vietnam day of that time is already locked. The payment is still posted.
- The payment description is the order code, and nothing else. PayOS limits that text to 9 characters when the bank account is not linked through PayOS, and the channel does not say which limit applies, so every description stays within 9 characters. The order code is still sent in full as `orderCode`. An order code that does not fit is not cut down and the link is not created. The signature uses that same description. A link that already exists is not sent again.
- Creating a link first reads the order code from PayOS. HTTP 404 is the only response that means the order does not exist, and only then is the link created. A 401, 403, 429, 500, a timeout, or a body whose code is not `00` leaves the item queued and does not create a link. The documented payment-request body has the order code, the amount and the status, and it does not include `checkoutUrl`. `checkoutUrl` is returned when the link is created. If a later read includes it and the order code and amount match, that URL is reused. If the order exists and `checkoutUrl` is absent, another link is not created: the item fails and `payos.poll` keeps watching that order. A timeout after PayOS created the link is retried by reading the order again. A link for a different amount fails the item. Missing credentials leave the item queued and the log says the secrets are not set; the same item continues after they are configured.
- A payment that PayOS reports as paid after the link was cancelled or expired is still confirmed.
- `/payment/payos/return` only tells the customer that PayOS has not confirmed the payment yet. It does not post money.
- Refunds are out of this feature. Recording the `account.payment` for a confirmed transaction is the payment feature.
- The portal sends the amount the customer entered. The link uses that amount when it is greater than zero and not more than the residual. A second request reuses the open link and does not change its amount.

## Sandbox

CI does not call PayOS. A sandbox check needs `PAYOS_CLIENT_ID`, `PAYOS_API_KEY` and `PAYOS_CHECKSUM_KEY` from PayOS's sandbox, not production keys. With those set and the provider published:

1. Start a link for part of an invoice and open the checkout URL.
2. Pay it in the sandbox. The return page must not post a payment.
3. The signed webhook posts one payment for the transferred amount. Sending it again does not post a second one.
4. The reconciliation day for that Vietnam date lists the transfer, and its printed total matches the payment.

Until that run is done, sandbox payment is unverified. Mocked webhook and client tests cover the same rules.

## Related documents

- [Accountant](../functional/ecommerce_module/features/accountant.md)
- [Scheduled jobs](scheduled-jobs.md)
- [Invoices](invoices.md)
- [E-commerce diagram](../infrastructure/database/ecommerce/ecommerce.prisma)
