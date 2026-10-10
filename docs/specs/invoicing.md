# Invoicing

Stories: US-A01, US-A02, US-A04, US-A05

## Goal

The accountant bills each order with an advance invoice when the quotation is sent and a final invoice for the rest, corrects a posted invoice with an adjustment invoice, and prints or downloads each invoice as a laboratory document. A posted invoice is never edited.

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

### Online payment

**Create payment link** on a posted advance or final invoice asks PayOS for the amount still owed and opens the link; the invoice lists its links with their status and the amount PayOS reported. [PayOS](payos.md) describes the link and how the money it brings is stored.

### Printing

`commerce.report_invoice` renders the invoice as a laboratory document with the company header: number and date, customer and supplier blocks, the invoice block (posted date, due date, total, amount owed), the lines, the tax per rate, the totals and the laboratory's bank accounts as payment details. The accountant prints or downloads it from the invoice; the customer portal and e-mailing are built by their own features.

### Permissions

Invoices and invoice lines are document types with the `read`, `create`, `edit` and `delete` permissions. The accountant role of the demo data holds them all; the sales role reads. The rules above hold for everyone, the administrator included.

## Related documents

- [Accountant](../functional/ecommerce_module/features/accountant.md), section 1
- [Payment and quotation](../business/payment-and-quotation.md)
- [Settings](settings.md)
- [PayOS](payos.md)
- [Permissions](permissions.md)
- [Database diagram](../infrastructure/database/ecommerce/ecommerce.prisma)
