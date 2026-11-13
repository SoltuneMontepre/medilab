# Payment and quotation

- Sending a quotation with an advance creates a payment request, not an invoice: it names the quotation version, the amount, the deadline and the payment means, and posts no receivable or revenue. Confirming the order of a customer not allowed to order on credit creates a payment request for the balance.
- The invoice is posted when the money is collected: verifying a payment posts an invoice for the amount received. For a customer allowed to order on credit, the final invoice is posted once testing is completed.
- A customer accepts a quotation with an advance when the verified payments reach the requested advance; a partial advance does not accept it. A quotation sent without an advance is accepted on the portal. There is no separate customer signature.
- A payment counts once it is verified: PayOS confirms online payments, the accountant confirms cash and bank transfers. While a payment awaits verification, a revision cannot be sent, the quotation cannot be declined and the order cannot be cancelled.
- Money received stays with the same order across revisions; the new request asks only for what is still needed. When the money already received covers a revised quotation's advance, the customer must still agree to the new version.
- A payment received before the payment deadline and verified after it still counts. Expiry stops new payments without cancelling the order or creating a refund.
- Prices exclude VAT; tax is added on the quotation and the invoice.
- Each quotation line uses the tax rate in force on the quotation date. The invoices of the order use the quotation's rates, so the customer pays the total they accepted.

## Related documents

- [Payment requests](../specs/payment-requests.md)
- [Sales order and customer order](sales-order-and-customer-order.md)
