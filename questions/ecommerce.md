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
- **Salesperson and invoices.** A salesperson's order shows the number of its invoices and its payment status, computed with full rights. The Invoices button opens Odoo's invoices, which only the accountant billing group and administrators read. Should the salesperson open the advance invoice of their own order from the order, read-only, or only see its status? Until it is answered, the button is hidden from salespeople. (US-S10)

## Related documents

- [Sales](../docs/functional/ecommerce_module/features/sales.md)
- [Accountant](../docs/functional/ecommerce_module/features/accountant.md)
