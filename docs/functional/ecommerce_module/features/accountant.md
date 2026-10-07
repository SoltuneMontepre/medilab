# Features of: Accountant

The accountant is the laboratory's financial user. The accountant issues and tracks invoices, confirms every payment, and reports on revenue and cash flow. The accountant does not set prices, quotations or approvals.

## I. User Stories

### Invoices

- **US-A01** As an accountant, I want to see every invoice, filtered by customer, status and date, so that I know what has been billed.
- **US-A02** As an accountant, I want to create the final invoice for an order, so that the customer is billed for the work done beyond the advance.
- **US-A03** As an accountant, I want advance invoices to be created and posted automatically when sales sends a quotation, so that I do not create them by hand.
- **US-A04** As an accountant, I want to send an invoice by email and download it as PDF, so that I can give the customer a document in the format they need.
- **US-A05** As an accountant, I want tax to be calculated according to the applicable rules, so that invoices comply with local regulations.

### Payments

- **US-A06** As an accountant, I want online payments to be recorded and matched to the invoice automatically, so that I do not enter them again.
- **US-A07** As an accountant, I want to record cash and bank-transfer payments against an invoice, so that the invoice shows the correct status.
- **US-A08** As an accountant, I want to confirm or reject the payments that sales recorded from customers, so that only verified money counts as paid.
- **US-A09** As an accountant, I want partial payments to be supported, so that a customer can pay an invoice in instalments.
- **US-A10** As an accountant, I want a payment receipt to be issued for every payment, so that the customer has proof of payment.
- **US-A11** As an accountant, I want to see the payment status of every order (not paid, partially paid, paid), so that I can follow up on what is owed.
- **US-A12** As an accountant, I want the system to remind customers of overdue payments, so that I do not chase them one by one.

### Reports and KPIs

- **US-A13** As an accountant, I want revenue, outstanding amounts and cash-flow reports for a period, so that I can manage the laboratory's finances.
- **US-A14** As an accountant, I want to export reports to a spreadsheet, so that I can use them in the laboratory's accounting records.
- **US-A15** As an accountant, I want to see how long payments take after an invoice is sent, so that I can measure collection performance.

## II. Feature Details

### 1. Invoices (US-A01 to US-A05)

| Invoice         | Created by                                                   | Purpose                                                                                  |
| --------------- | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| Advance invoice | System, when sales sends a quotation with an advance request | Collect the amount (full, percentage or fixed) the customer pays to accept the quotation |
| Final invoice   | Accountant, from the confirmed order                         | Bill the remaining amount once the work is done                                          |

- An advance invoice is posted automatically; the accountant does not need to create or post it.
- The final invoice deducts the advance already paid, so the customer is never billed twice for the same parameters.
- Invoices are sent by email with the PDF attached, and can be downloaded at any time. Customers see their posted invoices on the portal.
- Tax follows the configured tax rules and fiscal position for the customer. Prices in the catalog exclude VAT; the invoice shows net, tax and total separately.
- A posted invoice cannot be edited. A correction is made with a credit note (see the open questions).

Acceptance criteria:

- Sending a quotation with an advance request creates one posted advance invoice.
- The final invoice total equals the order total minus the advance.
- An invoice shows net, tax and total, and can be downloaded as PDF.

### 2. Payments (US-A06 to US-A12)

```mermaid
stateDiagram-v2
    [*] --> pending: sales records a cash or transfer payment
    pending --> confirmed: accountant confirms
    pending --> rejected: accountant rejects with a reason
    [*] --> confirmed: online payment confirmed by the gateway
    [*] --> confirmed: accountant records a payment directly
```

| Source                                            | How it is recorded                                                                                                                                                                                                                                        |
| ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Online payment                                    | The gateway confirms the payment with a signed notification; the system records it and matches it to the invoice. Returning to the website without that confirmation does not count as payment. A repeated notification does not create a second payment. |
| Cash or bank transfer, recorded by the accountant | The accountant selects the invoice, amount, date and method.                                                                                                                                                                                              |
| Cash or bank transfer, recorded by sales          | Sales creates a pending record; it counts only after the accountant confirms it.                                                                                                                                                                          |

Rules:

- **Partial payments.** A payment can be less than the amount due; the invoice is then partially paid and the remaining amount stays open. A payment cannot exceed the remaining amount.
- **Payment status.** Every order shows not paid, partially paid or paid, calculated from the confirmed payments on its posted invoices.
- **Receipts.** A receipt is issued for each confirmed payment and is available to the customer.
- **Pending amounts.** The accountant sees the pending amount per order so that a payment recorded by sales is not entered a second time.
- **Overdue reminders.** When an invoice passes its due date unpaid, the customer is reminded by their chosen notification channel at a fixed interval until it is paid; the accountant sees the list of overdue invoices.
- **Credit customers.** For a customer allowed to order on credit, an order can proceed without payment; the invoice then follows the normal due-date and reminder rules.

Acceptance criteria:

- A payment recorded by sales does not change the payment status until the accountant confirms it.
- A rejected payment returns the invoice to its previous status and notifies the salesperson with the reason.
- A repeated gateway notification for the same payment is ignored.
- A payment larger than the remaining amount is refused.

### 3. Reports and KPIs (US-A13 to US-A15)

| Report                 | Content                                                                 |
| ---------------------- | ----------------------------------------------------------------------- |
| Revenue                | Invoiced and collected amounts per period, customer and parameter group |
| Outstanding            | Unpaid and overdue invoices, with age of the debt                       |
| Cash flow              | Money received per period, per payment method                           |
| Collection performance | Time from invoice sent to payment, share of invoices paid on time       |

- Reports can be filtered by period and customer and exported to a spreadsheet.
- Reports use confirmed payments only; pending records are shown separately.

## IV. Related documents

- [E-commerce module overview](../overview.md)
- [Sales features](sales.md)
- [Customer features](customer.md)
