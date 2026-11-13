# Invoices

Stories: US-A01, US-A02, US-A03, US-A04, US-A05

## Goal

A laboratory invoice is an Odoo customer invoice (`account.move`): an advance invoice, a final invoice, or an adjustment. It is posted when the money is collected, or for a customer allowed to order on credit when testing is completed; a [payment request](payment-requests.md) is never an invoice. A posted invoice is never edited. What the customer still owes includes the posted adjustments.

## Design

- `invoice_kind` is `advance`, `final` or `adjustment`. It stays empty on journal entries that are not laboratory invoices.
- `order_id` points at the sale order. Sending a quotation with an advance creates no invoice: it creates the advance payment request.
- An advance invoice is Odoo's down payment invoice for the amount of one verified payment against the advance request. Verifying that payment posts the invoice, marks it `advance`, links it to the quotation and reconciles it with the payment, so it is paid when posted. A quotation revision never resets or cancels it.
- The final invoice is Odoo's remaining invoice with the down-payment deduction of every advance invoice. For a customer not allowed to order on credit, verifying the payment of the balance request posts it, reconciled with that payment, before sample collection. For a customer allowed to order on credit, the accountant posts it once testing is completed; it is due on the customer's payment terms. The final total is the order total minus the advances.
- A lowering adjustment is a credit note (`out_refund`) linked by `reversed_entry_id` and reconciled with the invoice, so `amount_residual` falls by the credit note. A raising adjustment is a new customer invoice linked by `adjusted_invoice_id`. The adjustment line uses the taxes of the invoice lines it corrects. The difference is the untaxed amount.
- The amount owed on an advance or final invoice is its `amount_residual` (already reduced by a reconciled credit note), plus the residual of its posted raising adjustments. The original invoice total stays as it was posted. A payment of that invoice cannot exceed its own residual.
- `button_draft` is refused on a posted laboratory invoice.
- The number comes from the sales journal sequence when the invoice is posted. That sequence restarts each year.
- The PDF is Odoo's invoice report. For a laboratory invoice it also shows the laboratory name and address, the invoice number and date, the customer, the invoice kind, the untaxed subtotal, each tax, the total, the amount already paid, the amount owed, and the laboratory bank accounts. The same report is printed, downloaded on the portal, and attached to the invoice email.
- Emailing a posted invoice queues one message, `invoice.sent`, with that PDF. A second send keeps the same message. The invoice's payment state does not change. The portal shows the amount owed on a final invoice or an adjustment.
- `is_overdue` is true for a posted final invoice or raising adjustment that is not fully paid and whose due date is before today in Asia/Ho_Chi_Minh. An unpaid payment request past its deadline is expired, not overdue.
- The portal lists and opens only posted customer invoices of the signed-in customer's commercial partner. Opening another customer's invoice URL returns to the portal home.
- `account.move` does not use the permission mixin: Odoo writes the invoice when it posts and reconciles it. Posting, adjusting and printing are limited to the accountant billing group and to administrators. Creating invoices from an order is also open to holders of the order's `order.invoice.all` permission: Odoo's Create Invoices dialog checks it and creates the draft with full rights. The adjustment wizard is a new model, so it uses the mixin and ships its permissions.

Verifying a payment against a payment request posts its advance or final invoice. For a customer allowed to order on credit, `sale.order.create_final_invoice` drafts the remaining invoice after testing. Emailing the posted invoice is `invoice.sent`.

## Related documents

- [Accountant](../functional/ecommerce_module/features/accountant.md)
- [Payment requests](payment-requests.md)
- [Module boundaries](../business/module-boundaries.md)
- [E-commerce diagram](../infrastructure/database/ecommerce/ecommerce.prisma)
