# PayOS

Stories: II.2 of the shared technical features (PayOS payments), US-A06

## Goal

The system takes online payments through PayOS: it creates a payment link for an invoice, learns of each transfer from PayOS's signed notification or from PayOS's own answer, keeps the link's status as PayOS reports it, and never loses the business action during a PayOS outage. The customer's browser returning to the website confirms nothing. The payments feature records the money from what this integration stored.

## Design

### Client and credentials

`services/payos_client.py` holds the client of the PayOS merchant API: create a payment link, get a link, cancel a link, confirm the webhook address, verify a notification. The credentials `PAYOS_CLIENT_ID`, `PAYOS_API_KEY` and `PAYOS_CHECKSUM_KEY` are read from the environment at call time and are never stored, logged or shown; `docs/infrastructure/secrets.md` says how Doppler provides them. Each call writes one line to the server log with the method, path and order code, and nothing else. `PayosError` carries PayOS's code and description; `PayosUnavailable`, a `PayosError`, means PayOS could not be reached or answered with a server error, which is worth retrying.

Signatures follow PayOS's own rule: the data as a `key=value&...` string with the keys sorted, `None` as empty, booleans in lower case and nested data as compact sorted JSON, signed with HMAC-SHA256 and the checksum key. A link creation is signed over the amount, cancel URL, description, order code and return URL; every answer and every notification is verified before it is used.

### Payment link

`medilab.payment.link` asks PayOS for an amount of a posted advance or final invoice, at most what is still owed. Its order code is an integer from the sequence `medilab.payment.link` (Code formats), unique, so a notification finds its link; the sequence is a standard one, never gapless, so a creation that rolls back after PayOS answered never reuses an order code PayOS may already know. Environments that share one PayOS merchant set their next numbers apart there. A link expires after the setting `payos_link_expiry_hours` (72 by default); the expiry is always sent to PayOS. Its description is the digits of the invoice code followed by its letters, cut to 9 characters, because PayOS limits the transfer content to 9 characters for bank accounts not linked through PayOS and banks drop spaces and slashes: `0001 26/HD` becomes `000126HD`, and a longer prefix is dropped before the number and the year.

Creating a link needs PayOS turned on (`payos_enabled`) and the three credentials in the environment; otherwise the user gets a clear message and nothing is queued. The call runs at once and under no row lock. When PayOS cannot be reached, the link stays `created` without a checkout page and the call is queued on the job `payos.calls` (`create:<id>`); any other refusal is shown to the user and the link is not kept. The accountant creates a link from the invoice for the full amount owed; the customer portal later creates links for the amount the customer chooses.

Each transfer PayOS reports is stored once as a `medilab.payment.link.transaction` by its bank reference, with its amount and time. PayOS gives the time without a timezone; it is read as Vietnam time and stored in UTC, and the transaction keeps its Vietnam day, which the reconciliation groups by. A link can receive several transfers; `amount_paid` is their sum.

### Statuses

A link is `created`, `pending`, `paid`, `failed`, `cancelled` or `expired`. PayOS's PENDING, PROCESSING and UNDERPAID map to `pending`, the others to their namesake. Statuses move forward only, in the order `created` < `pending` < {`cancelled`, `expired`, `failed`} < `paid`: a local `expired` (set by the poll) or `cancelled` (set by our cancel) is provisional, so a PAID that PayOS reports afterwards still wins and its money is recorded; once `paid`, nothing changes the status, and a CANCELLED or EXPIRED reported later is ignored.

`_apply_provider_update(transactions, status=None)` is the one place that stores what PayOS reported. It locks the invoice row first (`FOR NO KEY UPDATE`), stores the transfers not stored yet, moves the status, then calls `_record_payments()`, the hook of the payments feature, all with the context `payos_provider_update` that marks writes coming from PayOS. A notification carries one transfer and no link status, so the status follows the sum: `paid` when the transfers reach the amount, `pending` otherwise. The rule for every path that moves money: lock the invoice row first, then touch links, transactions and payments, and never call PayOS while the lock is held; PayOS calls that follow a money change go through the job queue.

### Webhook

`POST /medilab/payos/webhook` is public and exempt from CSRF. A body that is not JSON, or whose signature is missing or wrong, is refused with status 400 and changes nothing. A right signature applies the notification: an unknown order code is acknowledged with 200 and ignored, which is how PayOS's confirmation ping (order code 123) is answered; a code other than `00` is logged and acknowledged without storing anything; a successful transfer is stored once by its reference, so a repeated notification changes nothing the second time, and the poll is queued so PayOS's own status is confirmed. The address to register in the PayOS dashboard is `<web.base.url>/medilab/payos/webhook`.

`GET /medilab/payos/return` and `/medilab/payos/cancel` are the pages PayOS sends the customer back to. They only say that the payment is recorded once PayOS confirms it, or that it was cancelled; the portal replaces them.

### Jobs

- `payos.calls` (every 5 minutes) replays the calls an outage queued. `create:<id>`: create the link at PayOS; when PayOS refuses, the job asks PayOS whether the order code exists, because PayOS publishes no error code for "the order already exists" (`Đơn thanh toán đã tồn tại`). Found with the same amount: the timed-out first call succeeded, and the link adopts PayOS's id and status (its checkout page is derived from the id, since the lookup does not return it). Found with another amount: `PermanentJobError`, so the item fails at once and the administrator is told of a possible order-code collision between environments. Not found: the refusal is raised again and retried with the job's backoff. `cancel:<id>`: cancel at PayOS unless the link was paid meanwhile; a link PayOS no longer knows counts as cancelled.
- `payos.poll` (every 15 minutes) asks PayOS for each pending link, in case a notification was missed. Each check stores the full list of transfers PayOS returns, so a transfer whose notification was lost is still stored, and applies PayOS's status. A link still pending is checked again 15 minutes later. Sixty minutes after its expiry a link PayOS has not closed is marked `expired` locally and the polling ends; a PAID reported later still wins.

Both jobs call nothing while the credentials are missing from the environment: the item counts a failed attempt with that message and is retried, so an unconfigured server never calls PayOS with empty keys and the administrator sees the failed items once the attempts run out.

A link cancelled by the accountant is cancelled at PayOS at once, with the cancel queued when PayOS cannot be reached; a link never created at PayOS drops its queued creation instead.

### Settings

The E-commerce block holds `payos_enabled` (off by default), the payment methods PayOS offers, each on or off (`payos_method_qr_transfer`, the one method so far; the list is the constant `PAYMENT_METHODS`), and `payos_link_expiry_hours`. `_enabled_payment_methods()` gives the portal the methods to offer. The block warns when PayOS is on without credentials; it never shows a value.

### Permissions

A payment link has the `read`, `create` and `edit` permissions (edit covers cancelling) and no delete, since a link is evidence of what was asked of PayOS. A transaction has `read` only: PayOS creates them. The demo accountant holds them all; the demo sales role reads.

### Audit

Until the audit trail exists, the server log holds one line per PayOS call. The audit trail feature records each call with its order code and outcome, never the credentials or signatures.

## Related documents

- [Shared technical features](../functional/shared.md): II.2
- [Invoicing](invoicing.md)
- [Scheduled jobs](scheduled-jobs.md)
- [Settings](settings.md)
- [Secrets](../infrastructure/secrets.md)
- [Database diagram](../infrastructure/database/ecommerce/ecommerce.prisma)
