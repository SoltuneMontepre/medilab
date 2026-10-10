# E-commerce questions

- **Legal e-invoice.** Is the invoice the system issues the legal VAT e-invoice (hóa đơn điện tử under Decree 123/2020/NĐ-CP and amendments: the prescribed number and symbol format, the tax-authority code issued through an e-invoice provider, its adjustment and replacement rules), or an internal billing document while the legal e-invoice is issued elsewhere? The invoices feature builds the internal billing document until this is decided. (blocks US-A01, US-A02, US-A05)
- **Invoice and receipt numbers.** Invoices are numbered `0001 26/HD` and receipts `0001 26/PT` by default, restarting each year; the administrator changes the format in Code formats. Which abbreviation and symbol does the laboratory use, such as `HD-VTT`? (blocks US-A01, US-A10)
- **Invoice template.** A Trello card asks that administrators edit the invoice template themselves. The PDF is a fixed layout today. Is editing it on the screen wanted, and what may change: texts, logo, columns? (blocks US-A04)
- **Due date after posting.** The due date is fixed when the invoice is posted (the posting date plus the invoice due days setting). May the accountant extend it afterwards, and does an extension change the overdue reminders? (blocks US-A12)
- **Refunds.** If a customer paid an advance and the order is cancelled, who refunds and how is it recorded? (blocks US-S16, US-S17)
- **Credit notes.** How is a posted invoice corrected with a credit note? (blocks US-A02)
- **Samples in a parameter-first order.** Who groups the selected parameters into physical samples of the [test request](../docs/functional/laboratory_module/overview.md#test-requests-and-samples)? Sales would be the natural owner at quotation time.
- **Customer templates.** Can customers save their own orders as templates in the portal, or does only sales create templates for them? (blocks US-S09)
- **Sales data retention.** Orders, quotations and invoices older than a year could be archived and removed, keeping the last year in the system for trends. Which records, after how long, and does Vietnamese accounting law require keeping invoices longer in the system?

## Related documents

- [Sales](../docs/functional/ecommerce_module/features/sales.md)
- [Accountant](../docs/functional/ecommerce_module/features/accountant.md)
