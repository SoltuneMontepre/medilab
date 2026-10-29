# E-commerce questions

- **Refunds.** If a customer paid an advance and the order is cancelled, who refunds and how is it recorded? (blocks US-S16, US-S17)
- **Credit notes.** How is a posted invoice corrected with a credit note? (blocks US-A02)
- **Samples in a parameter-first order.** Who groups the selected parameters into physical samples of the [test request](../docs/functional/laboratory_module/overview.md#test-requests-and-samples)? Sales would be the natural owner at quotation time.
- **Customer templates.** Can customers save their own orders as templates in the portal, or does only sales create templates for them? (blocks US-S09)
- **Sales data retention.** Orders, quotations and invoices older than a year could be archived and removed, keeping the last year in the system for trends. Which records, after how long, and does Vietnamese accounting law require keeping invoices longer in the system?
- **Discounts.** Odoo discounts an order line by a percentage, and the whole order by a discount line. The documents also allow a fixed amount off a line. Is a percentage per line enough? (blocks US-S06)
- **Tax rates over time.** An Odoo tax has one rate. A change of rate for a period, such as VAT going from 10% to 8%, is a new tax put on the products for that period, and lines already priced keep their tax. Is that enough, or must the rate follow the quotation date by itself? (blocks US-AD18)
- **Tax of a line.** A parameter price and a package carry a MediLab tax, while an order line takes an Odoo tax from its product, and nothing links the two: a line added on the order form has no tax, and the demo sets taxes by hand. Which Odoo tax does a MediLab tax stand for on a line, and is it set when the price or package is saved? (blocks US-AD17, US-S06)
- **Package revenue over time.** The revenue report spreads a package line over its parameters by the package's parameters and prices of today, so a later change to a package or a parameter price moves past revenue between groups. Is that acceptable, or must each invoice line keep the spread of the day it was invoiced? (US-A14)
- **Support request deadline.** A support request's task is due 24 elapsed hours after it reaches the salesperson, nights and weekends included, and the administrator can change the default on the task type. This is the provisional default; it awaits formal confirmation, including whether only working hours should count. (blocks US-S20)
- **Priority surcharge.** A priority order makes its tests urgent. Does it cost more, and is the surcharge a line on the quotation?
- **Quotation layout.** What does the laboratory's báo giá show, and in what order: the header, the customer and contact, the salesperson, the lines by sample, the totals, the advance payment, the payment deadline and the signatures? A sample of the current paper form settles it. (blocks US-S07, asked of @nnh53)
- **PayOS checkout transaction.** Must the first payment request redirect directly to a newly created PayOS link, or may it show the pending page while a committed background job creates the link? Direct creation needs a transaction boundary that releases the invoice lock before the external call and preserves request retry and duplicate-click guarantees.
- **Catalog filter size.** Must the catalog offer every sample type and parameter group, including those without an offered product, or should those controls search or page a restricted set? A fixed result limit would hide existing choices.
- **Quotation and posting task deadlines.** A quotation task is due 24 elapsed hours after the order is submitted, and an invoice posting task 24 elapsed hours after the invoice is drafted, as for support requests. Are these the right defaults, and should only working hours count? (blocks US-S01, US-A02)
- **Quotation task for sales orders.** An order sales creates on behalf of a customer is claimed at once and gets no quotation task. Should it get one in its salesperson's to-do list, so every unsent quotation is a task? (blocks US-S02)
- **Orders already in the queue.** Orders submitted before quotation tasks existed have no task. Should the upgrade create one for each order still waiting in the queue or claimed and not quoted yet? (blocks US-S01)
- **Other waiting steps as tasks.** Which of these become tasks, for whom, when are they done, and with what deadline and schedule? (blocks SH-10)
  - A cash or transfer payment sales recorded, waiting for the accountant to confirm or reject it (US-A08).
  - An order whose approval sales requested, waiting for the Head of Sales to sign or reject it (US-S13).
  - A rejected order, waiting for its salesperson to correct it and request approval again (US-S14).
  - A sent quotation not paid by its payment deadline, waiting for its salesperson to follow up, extend it or let it expire (US-S10).
  - A completed order with something left to invoice, waiting for the accountant to create its final invoice (US-A02).
  - A posted invoice past its due date, waiting for the accountant to follow up beyond the automatic reminders (US-A12).
  - A support request about no order, waiting in the queue until a salesperson takes it (US-S20).
  - An account flagged as a possible duplicate, waiting for sales to clear or merge it (US-S04).
  - A day of PayOS transactions, waiting for the accountant to reconcile and lock it (US-A13).
- **Whole quantities on orders.** An order template line is a whole number of parameters or packages, but the order form and the cart only refuse a quantity below 1, so an order can still carry 1.5 tests and cannot then be saved as a template. Must an order line also be a whole number? (US-S09)

## Related documents

- [Sales](../docs/functional/ecommerce_module/features/sales.md)
- [Accountant](../docs/functional/ecommerce_module/features/accountant.md)
