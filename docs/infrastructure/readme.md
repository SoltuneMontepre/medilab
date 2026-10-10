# Infrastructure

- Database diagrams, one Prisma schema per module:
  - [Laboratory](database/laboratory/laboratory.prisma): master data, test requests, samples, results, signing, tasks, scheduling and the shared platform tables
  - [E-commerce](database/ecommerce/ecommerce.prisma): prices, taxes, service packages, orders, quotations, invoices, payments, support and feedback
  - [Inventory](database/inventory/inventory.prisma): stock items, locations and stores, lots, containers, moves, use per test, recipes, requisitions and transfers, stock takes, cost centres, budgets, charges, suppliers, purchase orders and receipts
- [Pipelines](pipelines.md): what each GitHub Actions workflow does, images, artifacts and caches
- [Secrets](secrets.md): Doppler config and the secrets published to GitHub
