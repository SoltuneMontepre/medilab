# Sales order and customer order

- Customers order by **parameter** or by **service package**. Sample types and parameter groups are catalog filters, not a first step.
- Every parameter has its own specific price in the catalog. The group does not set a price.
- A package has no price of its own: a package line costs the sum of the prices of the parameters it holds, times their quantities, in force on its pricing day. A package groups related parameters so they are ordered together.
- A package line retains the selected or resolved default way of testing for every included parameter. Each quotation version keeps the package line's price, its parameters and these selections; later catalog changes do not alter sent quotations or accepted orders, and creating sample tests uses the accepted selections, without rereading current package membership or defaults.
- A customer may untick parameters of a package or add other catalog parameters to it before adding it to the cart; the line's price follows the parameters it holds. A package keeps at least one parameter. A parameter added to a package is tested once per package.
- An order can mix package lines and single parameter lines.
- A package is not a quotation template. A template is a saved order a returning customer reuses to create the next order faster; it has no price of its own.
- Sales maintains customers. An order keeps the customer's requested date and the expected return date Sales promises on the quotation, the requested date when the standard turnaround meets it, or else fixed at sample receipt as the receipt day plus the turnaround. Only Sales changes the expected return date, with the customer's agreement. Each sample test has an internal due date; the customer sees the requested and committed dates, never an internal due date.
- Each line records its sample type and quantity, with a chosen or default way for every parameter. Accepted methods change only through a revised quotation and customer agreement; who performs a test, a department or a subcontractor, is internal and never shown to the customer.
- Sampling requirements calculate expected sample counts, containers and amounts. Confirming creates the request, expected samples and their sample tests; collection staff record the actual handover, including extra samples and excess material, for customer confirmation. Testing stays within the agreed scope: what is not tested stays with the sample and is returned only when the customer asks.
- From confirmation, an order's customer, prices, validity date, parameters and methods change only through a revised quotation the customer accepts. A confirmed order needs no further approval; only a quotation above the Head of Sales's thresholds is approved, before it is sent.
- A customer can cancel an order until it is confirmed; after that the customer can only request cancellation. Sales decides it before the samples are collected; once they are collected, cancelling goes through a change request the Head of Sales approves.

## Related documents

- [Payment and quotation](payment-and-quotation.md)
