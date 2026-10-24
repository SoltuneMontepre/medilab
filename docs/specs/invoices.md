# Invoices

Stories: US-A01, US-A02, US-A03, US-A04, US-A05

## Goal

A laboratory invoice is an Odoo customer invoice (`account.move`): an advance invoice, a final invoice, or an adjustment. A posted invoice is never edited. What the customer still owes includes the posted adjustments.

## Design

- `invoice_kind` is `advance`, `final` or `adjustment`. It stays empty on journal entries that are not laboratory invoices.
- `order_id` points at the sale order. Sending a quotation with an advance creates that invoice through the order's advance, marks it `advance`, and stores it on the quotation. An unpaid advance can still be reset and cancelled when the quotation is revised. A paid one cannot.
- An advance invoice is Odoo's down payment invoice. `sale.order.create_advance_invoice` creates it and posts it. Sending a quotation with an advance posts the same kind of invoice and keeps it on the quotation. `_on_quotation_sent` still posts an advance for a caller that uses it directly.
- `sale.order.create_final_invoice` drafts the remaining invoice with Odoo's down-payment deduction. The accountant posts it. The final invoice uses the quantities actually tested under the agreed quotation and revisions, then deducts the advance. When all ordered work is performed, this equals the order total minus the advance; a cancelled missing part is not billed as performed work.
- When the paid advance exceeds the total payable for performed work, there is no further amount to collect and the final invoice must not represent a negative customer charge. The accountant records the excess as an amount to refund, corrects posted invoices with credit notes as needed, and records the manual refund against the order and original payment. A credit note alone does not transfer money. No automatic refund or conversion to customer credit takes place.
- A lowering adjustment is a credit note (`out_refund`) linked by `reversed_entry_id` and reconciled with the invoice, so `amount_residual` falls by the credit note. A raising adjustment is a new customer invoice linked by `adjusted_invoice_id`. The adjustment line uses the taxes of the invoice lines it corrects. The difference is the untaxed amount.
- The amount to pay on each posted customer invoice is its own `amount_residual`, already reduced by reconciled credit notes. A raising adjustment is a separate posted invoice with its own payment action and residual; it is never added to the original invoice's payment target. Order and customer totals sum the outstanding invoices, including raising adjustments. The original invoice total stays as it was posted. A newly initiated payment of any invoice cannot exceed its own residual. An already-arrived PayOS transfer is recorded in full, with excess flagged for the accountant and no automatic refund, as the [payment rules](payments.md) specify.
- `button_draft` is refused on a posted laboratory invoice.
- The number comes from the sales journal sequence when the invoice is posted. That sequence restarts each year.
- The PDF is Odoo's invoice report. For a laboratory invoice it also shows the laboratory name and address, the invoice number and date, the customer, the invoice kind, the untaxed subtotal, each tax, the total, the amount already paid, the amount owed, and the laboratory bank accounts. The same report is printed, downloaded on the portal, and attached to the invoice email.
- Emailing a posted invoice queues one message, `invoice.sent`, with that PDF. A second send keeps the same message. The invoice's payment state does not change. The portal shows each invoice's own residual and lists raising adjustments separately with their own payment actions.
- `is_overdue` is true for a posted advance or final invoice that is not fully paid and whose due date is before today in Asia/Ho_Chi_Minh.
- The portal lists and opens only posted customer invoices of the signed-in customer's commercial partner. Opening another customer's invoice URL returns to the portal home.
- `account.move` does not use the permission mixin: Odoo writes the invoice when it posts and reconciles it. Posting, adjusting and printing are limited to the accountant billing group and to administrators. The adjustment wizard is a new model, so it uses the mixin and ships its permissions.

Sending a quotation creates the advance invoice and links it to the order. `sale.order.create_final_invoice` drafts the remaining invoice of a confirmed order. Emailing the posted invoice is `invoice.sent`.

## Related documents

- [Accountant](../functional/ecommerce_module/features/accountant.md)
- [Module boundaries](../business/module-boundaries.md)
- [E-commerce diagram](../infrastructure/database/ecommerce/ecommerce.prisma)
