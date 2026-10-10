# E-commerce questions

- **Refunds.** If a customer paid an advance and the order is cancelled, who refunds and how is it recorded? (blocks US-S16, US-S17)
- **Credit notes.** How is a posted invoice corrected with a credit note? (blocks US-A02)
- **Samples in a parameter-first order.** Who groups the selected parameters into physical samples of the [test request](../docs/functional/laboratory_module/overview.md#test-requests-and-samples)? Sales would be the natural owner at quotation time.
- **Customer templates.** Can customers save their own orders as templates in the portal, or does only sales create templates for them? (blocks US-S09)
- **Sales data retention.** Orders, quotations and invoices older than a year could be archived and removed, keeping the last year in the system for trends. Which records, after how long, and does Vietnamese accounting law require keeping invoices longer in the system?
- **Discounts.** Odoo discounts an order line by a percentage, and the whole order by a discount line. The documents also allow a fixed amount off a line. Is a percentage per line enough? (blocks US-S06)
- **Tax rates over time.** An Odoo tax has one rate. A change of rate for a period, such as VAT going from 10% to 8%, is a new tax put on the products for that period, and lines already priced keep their tax. Is that enough, or must the rate follow the quotation date by itself? (blocks US-AD18)
- **E-invoices.** Odoo Community includes Vietnamese e-invoicing through Viettel SInvoice (`l10n_vn_edi_viettel`). Must MediLab invoices be issued as e-invoices through it? (blocks US-A03, US-A05)
- **Public shop.** The portal catalog and cart are Odoo's eCommerce (`website_sale`), which installs the Website app. Is a public shop that visitors can browse before signing in wanted, or only the portal for signed-in customers? (blocks US-C08)

## Related documents

- [Sales](../docs/functional/ecommerce_module/features/sales.md)
- [Accountant](../docs/functional/ecommerce_module/features/accountant.md)
