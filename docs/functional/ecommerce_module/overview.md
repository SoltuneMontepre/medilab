# E-commerce Module Overview

In a testing laboratory, everything begins with a sale. Sales generates the lab's income and tracks every client order from the first request until the samples are ready to be collected. In MediLab the E-commerce module covers the customer portal, customer profiles, quotations, test requests, invoices, payments, tax calculation, discounts and sales analytics.

Dependencies: [core laboratory module](../laboratory_module/overview.md). It builds on Odoo's Sales, eCommerce, Invoicing, payment providers and the Vietnamese accounting localisation, as listed in [Module boundaries](../../business/module-boundaries.md#odoo-apps): an order is an Odoo sale order, an invoice is an Odoo invoice and a payment is an Odoo payment.

## Purpose

- Provides customer relationship management (CRM), sales capabilities and sales analytics so the lab can manage its sales process effectively.
- Provides customer profiles, a sales pipeline and performance metrics (KPI) to track and improve sales performance.
- Turns a customer's wish ("run these tests") into a priced, paid and approved order that the laboratory can execute.
- Provides customers with a self-service portal to place orders, track their status and download results.
- Provides accountants with tools to manage invoices, payments and tax compliance, along with reports and analytics to track the lab's cash flow.

## Main features

### I. Customer Portal

- Self-service portal where customers view their account information, place orders and track the order status.
- Secure login and authentication to protect customer data; customers only see their own documents.
- Responsive design that works on desktop and mobile.
- Test catalog with a cart: the customer selects parameters (tests) and service packages, filtered by sample type and parameter group. A parameter has its own price and a package has one price for all its parameters.
- Reorder a past order, request the cancellation of a confirmed order, and receive notifications at every step.

### II. Quotation Management

- Sales turns a submitted order into a quotation, reviews the parameters and prices, and sends it to the customer.
- Quotations can be revised; each revision keeps a link to the one it replaces.
- The customer accepts a quotation by paying the advance invoice, or declines it with a reason.
- A confirmed quotation becomes a sale order that goes through an internal approval chain (sales, then Head of Sales) before the laboratory collects samples.

### III. Test Request Management

- A confirmed sale order produces the test request that the laboratory core works on.
- Sales owns the commercial side of the request (customer, prices, payment status, approval); the core owns the testing side (samples, parameters, results).
- Sales follows the progress of each request and can cancel it while the laboratory has not completed any testing.

### IV. Invoices and Payments

- Advance and final invoices, with support for full, percentage and fixed-amount collection.
- Online payment, and cash or bank transfer recorded by the accountant; partial payments are supported.
- Payment status on every order: not paid, partially paid, paid.
- Invoices and receipts can be sent by email and downloaded as PDF.
- Tax calculation according to local regulations.

### V. Sales Analytics

- Sales pipeline: orders waiting to be claimed, quotations sent, awaiting payment, awaiting approval.
- Performance per salesperson and per period: quotations sent, accepted, approved, revenue.

### VI. Accounting & KPIs

- Revenue, outstanding payments and cash-flow reports for the accountant.
- KPI indicators for sales and approval turnaround, based on timestamps recorded at each step.

## Orders, quotations and invoices

The tables are drawn in [ecommerce.prisma](../../infrastructure/database/ecommerce/ecommerce.prisma).

| Rule             | Description                                                                                                                                    |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Cart             | A customer's draft order is their cart. Submitting it puts it in the sales queue.                                                              |
| Order lines      | An order line is one parameter or one package, with a quantity.                                                                                |
| Order lifecycle  | An order is draft, submitted, claimed, confirmed, completed or cancelled. Confirming it creates its test request in the Laboratory module; it is completed when that request's report is issued. Its approval by the Head of Sales follows its signatures. |
| Quotation lines  | When a quotation is priced, each line copies its catalog price, discount, tax and the tax rate in force on the quotation date, so a sent quotation never changes with the catalog. |
| Samples          | Sales groups a quotation's lines into the samples the customer will send; each line is tested on one sample. Confirming the order creates the test request with those samples. |
| Revisions        | A revision is a new quotation that replaces the previous one; the previous one becomes read-only.                                              |
| Numbers          | Orders, quotations, invoices and receipts get numbers from sequences whose format the administrator configures, such as `0001 26/BG-VTT` for quotations. Quotation, invoice and receipt numbers start again each year. |
| Invoices         | An invoice is an advance, final or adjustment invoice, and uses its quotation's prices and tax rates. The final invoice deducts the advance on a line of its own. A posted invoice is never edited; an adjustment invoice corrects it with only the difference. |
| Payments         | A payment is pending, confirmed or rejected; only confirmed payments count toward an invoice's paid amount. Each confirmed payment gets a receipt number. The order keeps its payment status (not paid, partially paid, paid) up to date. |
| Online payment   | Each online payment is a PayOS payment link for an invoice with a unique order code, so a repeated PayOS notification never records a second payment. |
| Templates        | An order template belongs to one customer and holds parameters, packages and quantities, without prices.                                      |
| Cancellation     | An order has at most one open cancellation request.                                                                                           |
| Support          | A support request is a conversation of messages between the customer and sales, optionally about one order.                       |
| Feedback         | A completed order has at most one feedback, a rating from 1 to 5 with a comment.                                                              |

## Actors

Each actor has its own feature document under `features/<actor>/`, listing the user stories, the feature details and the acceptance criteria for that actor.

| Actor | Role in the E-commerce module | Features |
| ----- | ------------------------ | -------- |
| Customer | Places orders, pays, tracks progress and downloads results | [customer](features/customer.md) |
| Sales | Claims orders, prepares and sends quotations, confirms orders, requests approval | [sales](features/sales.md) |
| Head of Sales | Approves or rejects confirmed orders, handles exceptions | Not written yet |
| Accountant | Records payments, manages invoices and reports | [accountant](features/accountant.md) |
| Administrator | Manages accounts, prices, taxes, service packages and settings | [admin](features/admin.md) |
