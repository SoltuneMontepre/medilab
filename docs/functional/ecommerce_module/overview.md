# E-commerce Module Overview

In a testing laboratory, everything begins with a sale. Sales generates the lab's income and tracks every client order from the first request until the samples are ready to be collected. In MediLab the E-commerce module covers the customer portal, customer profiles, quotations, test requests, invoices, payments, tax calculation, discounts and sales analytics.

Dependencies: [core laboratory module](../laboratory_module/overview.md). It builds on Odoo's Sales, Invoicing, payment providers and the Vietnamese accounting localisation, with its own public catalog and cart pages on Odoo's portal, as listed in [Module boundaries](../../business/module-boundaries.md#odoo-apps): an order is an Odoo sale order, an invoice is an Odoo invoice and a payment is an Odoo payment.

## Purpose

- Provides customer relationship management (CRM), sales capabilities and sales analytics so the lab can manage its sales process effectively.
- Provides customer profiles, a sales pipeline and performance metrics (KPI) to track and improve sales performance.
- Turns a customer's wish ("run these tests") into a priced, paid and confirmed order that the laboratory can execute.
- Provides customers with a self-service portal to place orders, track their status and download results.
- Provides accountants with tools to manage invoices, payments and tax compliance, along with reports and analytics to track the lab's cash flow.

## Main features

### I. Customer Portal

- Self-service portal where customers view their account information, place orders and track the order status.
- Secure login and authentication to protect customer data; customers only see their own documents.
- Responsive design that works on desktop and mobile.
- Public test catalog with a cart, open without signing in: the customer selects parameters (tests) and service packages, filtered by sample type and parameter group. A parameter has its own price and a package has one price for all its parameters. Submitting asks a visitor for their details and e-mail address.
- Reorder a past order, request the cancellation of a confirmed order, and receive notifications at every step.

### II. Quotation Management

- Sales prepares parameters, ways and prices. When a quotation's discount or total exceeds a threshold the Head of Sales sets, the Head of Sales approves it before Sales sends it; below the thresholds Sales sends it alone. This is the only approval of an order.
- Quotations can be revised; each revision keeps a link to the one it replaces.
- The customer accepts a quotation by paying the advance invoice, or declines it with a reason.
- Once the customer accepts, Sales confirms the sale order and the laboratory can collect samples. From confirmation, the order changes only through a revised quotation the customer accepts.
- Each quotation version keeps its package prices and package contents; later catalog changes do not alter it.
- An order keeps the customer's requested date and the committed return date Sales promises; the customer never sees the laboratory's internal due dates.

### III. Test Request Management

- A confirmed sale order produces the test request that the laboratory core works on.
- Sales owns the commercial side of the request (customer, prices, payment status, committed return date); the core owns the testing side (samples, parameters, results).
- Sales follows progress and handles whole-order cancellations or cancellation of an unfulfillable part. Completed results and unaffected work are preserved. Before samples are collected Sales decides alone; afterwards cancelling goes through a change request the Head of Sales approves.

### IV. Invoices and Payments

- Advance and final invoices, with support for full, percentage and fixed-amount collection.
- Online payment, and cash or bank transfer recorded by the accountant; partial payments are supported.
- Payment status on every order: not paid, partially paid, paid.
- Invoices and receipts can be sent by email and downloaded as PDF.
- Tax calculation according to local regulations.

### V. Sales Analytics

- Sales pipeline: orders by stage, from waiting to be claimed through draft, sent and unpaid and accepted to confirmed.
- Performance per salesperson and per period: quotations sent, accepted and declined, revenue, and the days between claim, quotation, payment and confirmation.

### VI. Accounting & KPIs

- Revenue, outstanding payments and cash-flow reports for the accountant.
- KPI indicators for sales turnaround, based on timestamps recorded at each step.

## Orders, quotations and invoices

The tables are drawn in [ecommerce.prisma](../../infrastructure/database/ecommerce/ecommerce.prisma).

| Rule             | Description                                                                                                                                    |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Cart             | A customer's or visitor's draft order is their cart. Submitting it puts it in the sales queue; a visitor gives their details and e-mail address first. |
| Order lines | An order line selects a parameter or whole service package, a sample type and a quantity. It retains the selected or resolved default way for each included parameter. Catalog membership and default changes do not rewrite accepted selections; sample tests use them, and changes require a revised quotation and customer agreement. |
| Order lifecycle  | An order is draft, submitted, claimed, confirmed, completed or cancelled. Confirming it creates its test request in the Laboratory module and freezes its content, which then changes only through a revised quotation the customer accepts; it is completed when that request's report is issued. |
| Quotation lines  | When a quotation is priced, each line copies its catalog price, discount, tax and the tax rate in force on the quotation date, so a sent quotation never changes with the catalog. |
| Samples | Sampling requirements determine the expected physical samples, containers and amounts shown when ordering. For each type, objects equal the largest line quantity, and expected samples equal objects times compatible sampling groups. Confirming creates these expected samples and their sample tests; collection staff record the actual handover for customer confirmation. Testing stays within the agreed scope: extra samples and excess material add no test. |
| Revisions        | A revision is a new quotation that replaces the previous one; the previous one becomes read-only.                                              |
| Dates | An order keeps the customer's requested date and the committed return date Sales promises on the quotation, by default the requested date when the laboratory can meet it and otherwise the estimate. Only Sales changes the committed date, with the customer's agreement. Each sample test has an internal due date the customer never sees. |
| Numbers          | Orders, quotations, invoices and receipts get numbers from sequences whose format the administrator configures, such as `0001 26/BG-VTT` for quotations. Quotation, invoice and receipt numbers start again each year. |
| Invoices         | An invoice is an advance, final or adjustment invoice, and uses its quotation's prices and tax rates. The final invoice deducts the advance on a line of its own. A posted invoice is never edited; an adjustment invoice corrects it with only the difference. Invoices are Odoo invoices and are not issued through an e-invoice provider. |
| Payments         | A payment is pending, confirmed or rejected; only confirmed payments count toward an invoice's paid amount. Each confirmed payment gets a receipt number. The order keeps its payment status (not paid, partially paid, paid) up to date. |
| Online payment   | Each online payment is a PayOS payment link for an invoice with a unique order code, so a repeated PayOS notification never records a second payment. |
| Templates        | An order template belongs to one customer and holds parameters, packages and quantities, without prices.                                      |
| Cancellation | An order has at most one open cancellation request. A request may cover the whole order or an unfulfillable part; Sales records its decision and preserves work outside the accepted cancellation scope. Once samples are collected, cancelling goes through a change request the Head of Sales approves. |
| Support          | A support request is a conversation of messages between the customer and sales, optionally about one order.                       |
| Feedback         | A completed order has at most one feedback, a rating from 1 to 5 with an optional comment.                                                              |

## Actors

Each actor has its own feature document under `features/<actor>/`, listing the user stories, the feature details and the acceptance criteria for that actor.

| Actor | Role in the E-commerce module | Features |
| ----- | ------------------------ | -------- |
| Customer | Places orders, pays, tracks progress and downloads results | [customer](features/customer.md) |
| Sales | Claims orders, prepares and sends quotations, confirms orders | [sales](features/sales.md) |
| Head of Sales | Approves quotations above the thresholds and cancellations of orders whose samples are collected, handles exceptions | Not written yet |
| Accountant | Records payments, manages invoices and reports | [accountant](features/accountant.md) |
| Administrator | Manages accounts, prices, taxes, service packages and settings | [admin](features/admin.md) |
