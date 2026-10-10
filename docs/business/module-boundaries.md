# Module boundaries

- E-commerce and Inventory depend on Laboratory; Laboratory depends on neither.
- No module depends on any Odoo module other than `base`, `web`.
- Customers, tasks and schedules belong to Laboratory, so they work without E-commerce. E-commerce keeps prices, taxes, service packages and each customer's sales terms.
- Machines and chemical information belong to Laboratory. Departments and their teams belong to Laboratory. Inventory manages stock, stores, containers and their expiry, movement between stores, recipes, suppliers and purchasing, cost centres and budgets, how much of each item one test of a method uses, and which containers and lots each test result used.

## Related documents

- [Overview](../functional/index.md)
