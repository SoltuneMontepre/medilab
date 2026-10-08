# Module boundaries

- E-commerce and Inventory depend on Laboratory; Laboratory depends on neither.
- No module depends on any Odoo module other than `base` and `web`. A [people data source](approval-and-signing-chain.md#people-data-source) that reads another Odoo app, such as HR, is its own module that depends on Laboratory and that app.
- Machines and chemical information belong to Laboratory. Inventory manages chemical stock, expiry dates, internal movement, suppliers and how much of each chemical one test of a method uses.

## Related documents

- [Overview](../functional/index.md)
