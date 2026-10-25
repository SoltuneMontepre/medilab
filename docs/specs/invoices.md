# Invoices

Stories: US-A01, US-A02, US-A03, US-A04, US-A05

## Goal

Record service billing and corrections separately from a request for an advance and from receipt of money. Laboratory customer invoices use Odoo's accounting documents. They can be emailed and downloaded, but this scope does not integrate a tax-authority e-invoice provider. Viettel Sign signs supported documents and does not turn an internal invoice into a tax-authority e-invoice.

## Design

### Requests, receipts and service billing

- Sending a quotation with an advance creates a [payment request](payment-requests.md), not a posted invoice, receivable or revenue. There is no posted advance invoice to reset or cancel when that request is replaced.
- Verification of a receipt records the money actually received and the customer's advance for the order. Receiving money alone does not recognize revenue or require automatic posting of a customer invoice.
- When the service meets the conditions for revenue recognition, record revenue and the receivable and offset verified advances already received, even if the customer has not paid in full. Keep the service amount, tax, money received and remaining amount distinct.
- Bill the quantities actually tested under the agreed quotation and revisions. Missing cancelled samples are not billed as performed work; extras need the agreed revision. For fully performed work, the remaining collection is the agreed total payable less the money already applied, without collecting or recognizing the same amount twice.
- A posted invoice is never reset, edited or cancelled to revise a quotation. Correct it through an adjustment or credit note. An advance payment request and an invoice are different documents.

### Adjustments and refunds

- A lowering adjustment is a credit note linked to the invoice. Reconciliation reduces that invoice's remaining amount. A raising adjustment is a separate posted customer invoice linked to the original.
- Each invoice's payment action uses only its own residual. A raising adjustment has its own payment action; it never increases the original invoice's payment target. Order and customer debt summaries include every outstanding invoice.
- If verified money received exceeds the total payable for performed work after agreed cancellation, collect nothing further. Record the excess for manual refund by the accountant, correct posted invoices with credit notes as needed, and link the refund to the order and original receipt. A credit note does not transfer money. Do not refund automatically or convert the excess into credit for another order.
- Expiry alone does not create a refund obligation. Keep a partial advance on the same order while Sales agrees continuation, revision or cancellation.

### Prices, presentation and access

- Preserve the agreed service price before VAT. Show the service amount, applicable tax, total, verified money applied and remaining amount separately. A quotation's displayed tax is a version snapshot, not a commitment that later billing keeps that rate.
- Retain each invoice's order, source quotation and correction links. Posting assigns its journal-sequence number; numbering starts again each year.
- The PDF shows laboratory name and address, invoice number and date, customer, kind, service subtotal, tax, total, money applied, remaining amount and laboratory bank accounts. Printing, portal download and invoice email use the same invoice PDF.
- Emailing a posted invoice queues one `invoice.sent` message with the PDF. A repeat send keeps the same message and does not change payment status. The portal lists raising adjustments separately.
- An invoice is overdue when it is posted, still has a residual and its due date is before today in Asia/Ho_Chi_Minh. An expired advance request is not an overdue posted invoice.
- The portal lists and opens only posted invoices of the signed-in customer's commercial partner, with the existing authorized invoice-token access. An unauthorized request never exposes another customer's invoice.
- Posting, correcting and printing remain limited to the accountant billing group and administrators. Odoo writes `account.move` during posting and reconciliation; it does not use the permission mixin. New correction models ship the required permission records.

## Acceptance criteria

- Sending a 5,400,000 VND advance request with no receipt creates no posted customer invoice or invoice debt.
- Verifying a 2,000,000 VND advance records that receipt without treating it as service revenue.
- When service recognition conditions are met, billing and offsetting the advance do not depend on collection of the entire balance.
- A reconciled 500,000 VND lowering credit note against a 5,000,000 VND residual leaves 4,500,000 VND payable; the original posted amount is retained.
- An original residual of 5,000,000 VND and a raising adjustment of 2,000,000 VND give 7,000,000 VND total debt and two separate payment targets.
- An 8,000,000 VND verified advance against 5,000,000 VND total payable leaves 3,000,000 VND for manual refund. Recording its credit note does not mark the money as refunded.

## Related documents

- [Accountant](../functional/ecommerce_module/features/accountant.md)
- [Payment and quotation](../business/payment-and-quotation.md)
- [Payment requests](payment-requests.md)
- [Payments and reconciliation](payments.md)
- [Module boundaries](../business/module-boundaries.md)
- [E-commerce diagram](../infrastructure/database/ecommerce/ecommerce.prisma)
