# E-commerce questions

- **Refunds.** If a customer paid an advance and the order is cancelled, who refunds and how is it recorded? (blocks US-S16, US-S17)
- **Credit notes.** Decided: a posted invoice is corrected with an adjustment invoice that holds only the difference; a lowering adjustment is a credit note, as [Accountant](../docs/functional/ecommerce_module/features/accountant.md) and the [invoices spec](../docs/specs/invoices.md) say.
- **Samples in a parameter-first order.** Who groups the selected parameters into physical samples of the [test request](../docs/functional/laboratory_module/overview.md#test-requests-and-samples)? Sales would be the natural owner at quotation time.
- **Customer templates.** Can customers save their own orders as templates in the portal, or does only sales create templates for them? (blocks US-S09)
- **Sales data retention.** Orders, quotations and invoices older than a year could be archived and removed, keeping the last year in the system for trends. Which records, after how long, and does Vietnamese accounting law require keeping invoices longer in the system?
- **Fixed-amount discounts.** For now discounts are percentages only, as [Requirements changed](requirements-changed.md) says. Will sales later need a fixed amount off a line or off the whole quotation?
- **Tax rates over time.** An Odoo tax has one rate, and invoices copy the taxes of the quotation's lines. Under Vietnamese law the VAT rate follows each invoice's own date instead: the advance invoice takes the rate of the day the advance is received, and the final invoice the rate of the day the service is completed, on the remaining value only. Which rule do invoices follow, and do quoted prices exclude VAT so the total can change with the rate? Researched in [#214](https://github.com/SoltuneMontepre/medilab/issues/214#issuecomment-6311694472). (blocks US-AD18)
- **Advance invoices and revised quotations.** Since Nghị định 254/2026/NĐ-CP, money collected before a service is invoiced when it is collected, and an invoice is an e-invoice registered with the tax authority. Is the advance a payment request until it is paid, what does revising, declining or letting a quotation expire do to an unpaid advance, a pending payment and an open PayOS link, and where is the legal e-invoice issued? See [#214](https://github.com/SoltuneMontepre/medilab/issues/214). (US-A03)
- **Correcting a confirmed payment.** A pending payment is confirmed or rejected, but nothing corrects a confirmed payment recorded with the wrong amount, date or method. Is it reversed and recorded again, or edited while its reconciliation day is not locked? (US-A08, US-A13)
- **Partial advance payment.** Paying the advance accepts the quotation. Does paying part of the advance accept it, or does the quotation wait for the whole advance?
- **Rejecting a paid order.** The Head of Sales can reject an order whose advance the customer has paid; the documents only let the salesperson correct it and ask again. What happens to the order and to the paid advance when the Head of Sales rejects it for good? (US-S13)
- **Package revenue over time.** The revenue report spreads a package line over its parameters by the package's parameters and prices of today, so a later change to a package or a parameter price moves past revenue between groups. Is that acceptable, or must each invoice line keep the spread of the day it was invoiced? (US-A14)
- **Support request deadline.** A support request's task is due 24 elapsed hours after it reaches the salesperson, nights and weekends included, and the administrator can change the default on the task type. This is the provisional default; it awaits formal confirmation, including whether only working hours should count. (blocks US-S20)
- **Priority surcharge.** A priority order makes its tests urgent. Does it cost more, and is the surcharge a line on the quotation?

## Related documents

- [Sales](../docs/functional/ecommerce_module/features/sales.md)
- [Accountant](../docs/functional/ecommerce_module/features/accountant.md)
