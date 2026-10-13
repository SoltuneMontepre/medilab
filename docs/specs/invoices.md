# Invoices

Stories: US-A01, US-A02, US-A03, US-A04, US-A05

## Goal

A laboratory invoice is an Odoo customer invoice (`account.move`): an advance invoice, a final invoice, or an adjustment. A posted invoice is never edited. What the customer still owes includes the posted adjustments.

## Design

- `invoice_kind` is `advance`, `final` or `adjustment`. It stays empty on journal entries that are not laboratory invoices.
- `order_id` points at the sale order. It may be empty, because the order screens are not part of this change; the invoice lines still link the order through Odoo's sale lines.
- An advance invoice is Odoo's down payment invoice. `sale.order.create_advance_invoice` creates it and posts it. Sending a quotation does not live here: that flow calls `sale.order._on_quotation_sent`, which posts the same advance invoice.
- `sale.order.create_final_invoice` drafts the remaining invoice with Odoo's down-payment deduction. The accountant posts it. On an order created for this purpose, the final total is the order total minus the advance.
- A lowering adjustment is a credit note (`out_refund`) linked by `reversed_entry_id` and reconciled with the invoice, so `amount_residual` falls by the credit note. A raising adjustment is a new customer invoice linked by `adjusted_invoice_id`. The adjustment line uses the taxes of the invoice lines it corrects. The difference is the untaxed amount.
- The amount owed on an advance or final invoice is its `amount_residual` (already reduced by a reconciled credit note), plus the residual of its posted raising adjustments. The original invoice total stays as it was posted. A payment of that invoice cannot exceed its own residual.
- `button_draft` is refused on a posted laboratory invoice.
- The number comes from the sales journal sequence when the invoice is posted. That sequence restarts each year.
- The PDF is Odoo's invoice report, with the invoice kind and, for an advance or final invoice, the amount owed.
- The portal lists and opens only posted customer invoices of the signed-in customer's commercial partner. Opening another customer's invoice URL returns to the portal home.
- `account.move` does not use the permission mixin: Odoo writes the invoice when it posts and reconciles it. Posting, adjusting and printing are limited to the accountant billing group and to administrators. The adjustment wizard is a new model, so it uses the mixin and ships its permissions.

Sending the quotation, emailing the invoice, and tying the final invoice to a real customer order are later features.

## Related documents

- [Accountant](../functional/ecommerce_module/features/accountant.md)
- [Module boundaries](../business/module-boundaries.md)
- [E-commerce diagram](../infrastructure/database/ecommerce/ecommerce.prisma)
