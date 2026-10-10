# Invoicing

Stories: US-A01, US-A02, US-A04 to US-A13

## Goal

The accountant bills each order with an advance invoice when the quotation is sent and a final invoice for the rest, corrects a posted invoice with an adjustment invoice, and prints or downloads each invoice as a laboratory document. A posted invoice is never edited. Payments against an invoice come from PayOS or are recorded by hand; only payments the accountant confirms count, each confirmed payment has a receipt, and the accountant reconciles each day's PayOS transfers and locks the day.

## What the invoice is

`medilab.invoice` is the laboratory's billing document: the amounts it asks the customer for, with tax, and what has been paid against it. It is not the legal VAT e-invoice (hóa đơn điện tử under Decree 123/2020/NĐ-CP and its amendments), which has its own number and symbol format, is issued through an e-invoice provider with a tax-authority code, and follows its own adjustment and replacement rules. Issuing the legal e-invoice is a separate integration the owner has not decided on yet (see the open question in `questions/ecommerce.md`).

## Design

### Invoices and lines

- An invoice (`medilab.invoice`) has a kind, `advance`, `final` or `adjustment`, a status, `draft`, `posted` or `cancelled`, the contact billed, its lines, and the dates it was posted and is due. Until orders and quotations exist, the contact billed is set on the invoice itself; the orders feature derives it from the order's customer and adds the order and quotation the invoice bills.
- A line (`medilab.invoice.line`) has a description, a kind, `line`, `advance` or `advance_deduction`, its net amount, its tax rate in percent and its tax. The tax of a line is its net amount times its rate, rounded by the currency; the invoice's net, tax and total add up the lines' rounded amounts, and the tax per rate on the PDF groups the same rounded amounts, so every figure printed adds up. An advance deduction is negative; other lines are negative only on an adjustment invoice.
- Every amount is in VND (`medilab.vnd.mixin`).

### Posting

Posting a draft invoice needs at least one line. It stamps the posting time, takes the next number from the sequence `medilab.invoice` for the posting date, and sets the due date when none was given: the posting date plus the setting `invoice_due_days` (7 by default, in the E-commerce block of the MediLab settings). Numbers follow the format the administrator configures in Code formats, `0001 26/HD` by default, and restart each year.

A posted invoice is frozen: only the fields the sending feature keeps (`sent_at`, `attachment_id`) can still change, its lines cannot be added, changed or removed, and it cannot be deleted. A draft can be changed, cancelled or deleted; a cancelled invoice is frozen like a posted one.

### Adjustments

An adjustment invoice corrects one posted advance or final invoice of the same customer and holds only the difference, as positive or negative lines. It is posted and printed like any other invoice. The amount owed on the corrected invoice is its total plus the totals of its posted adjustments; the payments feature deducts the confirmed payments from it. An adjustment cannot take that amount below zero, and an adjustment invoice itself owes nothing: payments are recorded on the corrected invoice only.

### Payments

A payment (`medilab.payment`) is recorded on a posted advance or final invoice, never on an adjustment: payments go on the invoice the adjustment corrects, and the adjustment mirrors its payment status. It has an amount, a date, a method (`online`, `bank_transfer` or `cash`) and a status: `pending`, `confirmed` or `rejected`. Only confirmed payments count: the invoice's `amount_paid` is their sum, `amount_pending` the sum of the pending ones (shown so a payment sales recorded is not recorded again), and `amount_owed` is the total plus the adjustments minus the confirmed payments. The payment status is `not_paid`, `partially_paid` or `paid` from the confirmed payments; a posted invoice not paid by its due date is overdue, and the invoice list filters overdue invoices. Reminders belong to the notifications feature.

- **Who records what.** A user who holds the `edit` permission on payments (the accountant) records a payment confirmed at once; anyone else with `create` (sales) records a pending payment, which the accountant confirms, or rejects with a reason, which notifies the salesperson (a hook until notifications exist). **Register payment** on the invoice opens the form with the invoice and the amount still owed.
- **Manual payments never exceed what is owed.** A cash or bank transfer payment larger than the amount still owed is refused when it is recorded and again when it is confirmed, so two pending payments cannot both be confirmed above the owed amount. **Online payments are exempt**: money PayOS confirmed is always recorded, even after a manual payment settled the invoice meanwhile. The payment that takes the owed amount below zero is stored with `is_overpaying`, decided once under the lock and never recomputed, and the invoice shows it is overpaid; earlier payments and links stay as they were. Refunds are out of scope.
- **Online payments come only from PayOS transactions**, one payment per transfer, created confirmed by `_record_payments()` under the invoice row lock with the transfer's amount and Vietnam day; the transfer's unique reference and its unique payment make this safe to repeat, so repeated notifications and new polls create nothing. Once every transfer of a link has its payment, the sum of the link's online payments equals the link's `amount_paid`. Nobody records an online payment by hand.
- **Lock order.** Every path that moves money locks the invoice row first (`FOR NO KEY UPDATE`), re-reads the owed amount under the lock and only then writes payments, links and transactions: recording and confirming a payment, applying what PayOS reported, recording the missing payments of a link. No PayOS call runs while the lock is held: when a confirmed payment settles the invoice, its other open links are cancelled through the `payos.calls` queue (`cancel:<id>`), and the link stays pending until the job cancels it, a PAID reported meanwhile still winning. The automated test only checks that the lock statement is issued and that two sequential confirmations above the owed amount end with the second refused; correctness under concurrency rests on this lock design.
- **Frozen.** A confirmed or rejected payment keeps its invoice, amount, date, method and link; only a pending payment can be deleted.

### Receipts

Confirming a payment numbers it from the sequence `medilab.payment.receipt` (`0001 26/PT` by default, restarting each year, in Code formats) and stores its receipt (`commerce.report_receipt`: payer, invoice, method, amount, what is still owed, who confirmed it) as an attachment, so the customer can download the same document later. The accountant prints it from the payment.

### Online payment

**Create payment link** on a posted advance or final invoice asks PayOS for the amount still owed and opens the link; the invoice lists its links with their status and the amount PayOS reported. [PayOS](payos.md) describes the link and how the money it brings is stored.

### Reconciliation

A reconciliation day (`medilab.reconciliation.day`) is one Vietnam day of PayOS transfers; its rows are the transactions of that day, each with its reference, time, amount, link, invoice, payment and state:

| State | Meaning | What unblocks the lock |
| --- | --- | --- |
| `missing_payment` | A transfer PayOS reported that has no payment yet | **Record payments** on the row creates the missing payments of that link, one per transfer, on the right invoice; it needs the `edit` permission on payments |
| `underpaid` | Every transfer of the link has its payment, but the link received less than it asked for and is not paid | An acknowledgement on the link, with a reason, given for the amount paid so far; a later transfer changes that amount, so its day needs a new acknowledgement |
| `overpaying` | The row's payment took the invoice's owed amount below zero | An acknowledgement on that payment, with a reason |
| `matched` | The transfer has its payment and nothing is off | Nothing |

There is no "payment without a transaction" state: online payments exist only from stored transactions. A day locks when no row is `missing_payment` and every `underpaid` or `overpaying` row is acknowledged; the lock records who locked it and when, and the report (`commerce.report_reconciliation_day`) prints the rows with their state, the acknowledgements with who, when and why, and the day's PayOS total. Acknowledging needs the `edit` permission on reconciliation days and applies to that row only: a later overpayment on another link of the same invoice never changes an earlier row.

Once a day is locked, its online payments, transactions and the provider fields of its links cannot be changed by anyone, and the day itself cannot be changed, deleted or unlocked (the owner has a question on unlocking). The one exception is PayOS itself: what the webhook or the poll reports for a locked day is still stored, with the context `payos_provider_update`, and its payment is shown as recorded after the lock, so a late confirmation is never lost and is visible as such. Cash and bank transfer payments are not part of the day and stay editable while pending.

### Printing

`commerce.report_invoice` renders the invoice as a laboratory document with the company header: number and date, customer and supplier blocks, the invoice block (posted date, due date, total, amount owed), the lines, the tax per rate, the totals and the laboratory's bank accounts as payment details. The accountant prints or downloads it from the invoice; the customer portal and e-mailing are built by their own features.

### Permissions

Invoices, invoice lines and payments are document types with the `read`, `create`, `edit` and `delete` permissions; a reconciliation day has `read`, `create` and `edit`, since a locked day is never deleted. The accountant role of the demo data holds them all; the sales role reads invoices and payments and creates (pending) payments. The rules above hold for everyone, the administrator included.

## Related documents

- [Accountant](../functional/ecommerce_module/features/accountant.md), sections 1 and 2
- [Payment and quotation](../business/payment-and-quotation.md)
- [Settings](settings.md)
- [PayOS](payos.md)
- [Permissions](permissions.md)
- [Database diagram](../infrastructure/database/ecommerce/ecommerce.prisma)
