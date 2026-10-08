# Sales order and customer order

- Customers order by **parameter** or by **service package**. Sample types and parameter groups are catalog filters, not a first step.
- Every parameter has its own specific price in the catalog. The group does not set a price.
- A package has its own price; a package line in an order uses the package price, not the sum of its parameters.
- A package is ordered whole. To drop one of its parameters, the package is removed and the wanted parameters are added one by one.
- An order can mix package lines and single parameter lines.
- A package is not a quotation template. A template is a saved order a returning customer reuses to create the next order faster; it has no price of its own.
- A customer can cancel an order until it is confirmed; after that the customer can only request cancellation, and sales decides.

## Related documents

- [Payment and quotation](payment-and-quotation.md)
