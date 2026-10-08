# Module boundaries

- E-commerce and Inventory depend on Laboratory; Laboratory depends on neither.
- No module depends on any Odoo module other than `base` and `web`.
- Machines and chemical information belong to Laboratory. Inventory manages chemical stock, expiry dates, internal movement, suppliers and how much of each chemical one test of a method uses.

## Related documents

- [Overview](../functional/index.md)
