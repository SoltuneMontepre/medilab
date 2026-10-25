# Payment and quotation

- Sending a quotation with an advance request creates a payment request, not a posted invoice, receivable or revenue. The request identifies the quotation version, amount, deadline and payment instructions.
- Verification of money received records the receipt and the customer's advance for its actual amount. Receiving an advance alone does not recognize revenue. When the service meets the conditions for revenue recognition, record the revenue and receivable and offset the money already received, even if the customer has not paid in full.
- A quotation requiring an advance is automatically accepted only when the verified receipts applied to that version reach its required advance. Partial receipts remain recorded without accepting the quotation. A pending payment and a browser return do not count as verified receipts.
- If money from an earlier version already covers a revised quotation's advance, the customer must explicitly agree to the new version through the portal or evidence saved by Sales. Money alone does not establish agreement to different terms.
- An order with an advance requirement needs the full verified advance, customer acceptance and completed order approval before collection or testing starts. Credit permission does not waive that requirement.
- Agreed service prices exclude VAT and stay fixed when the applicable VAT rate changes; the total payable changes with the applicable tax. Preserve the amounts shown on each sent version. When VAT changes before payment, Sales sends a new quotation version showing the new tax, total and advance.
- Sales may draft a revision while a receipt awaits verification, but sending the replacement waits until the accountant has confirmed or rejected the pending receipts. Money received stays with the same order; it is not silently refunded or transferred to another order.
- Sending a replacement stops the old payment request and asks PayOS to cancel its open links. A cancelled link does not guarantee that no money can arrive. Verify and record an actual transfer once, then have the accountant review a transfer discovered through an old link before applying it to the revised request.
- Expiry stops new payment initiation and requests cancellation of open links. Sales must extend the quotation or send a replacement before requesting payment again. Verification after expiry may accept an unchanged, non-declined quotation if the full advance actually arrived before the deadline and the order has not been cancelled.
- A partial receipt retained when the quotation expires stays on the same order while Sales agrees an extension, revision or cancellation with the customer. Expiry alone creates no refund obligation. An excess over the total payable after agreed cancellation is recorded for manual refund; a credit note is not evidence that money was returned.

## Related documents

- [Payment requests](../specs/payment-requests.md)
- [Invoices](../specs/invoices.md)
- [Payments and reconciliation](../specs/payments.md)
- [Sales order and customer order](sales-order-and-customer-order.md)
