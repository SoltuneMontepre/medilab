# Infrastructure

- [Architecture](architecture.md): production on two VPSes and an Azure witness, starting on Server A alone, Argo CD, database failover, object storage, backups, ingress through Cloudflare Tunnel and MQTT
- Database diagrams draw Odoo tables, one Prisma schema per module; required business relationships are in the [conceptual model](../functional/conceptual-model.md):
  - [Laboratory](database/laboratory/laboratory.prisma): master data, test requests, samples, results, signing, tasks, scheduling and the shared platform tables
  - [E-commerce](database/ecommerce/ecommerce.prisma): prices, taxes, service packages, orders, quotations, invoices, payments, support and feedback
  - [Inventory](database/inventory/inventory.prisma): stock items, locations and stores, lots, containers, moves, use per test, recipes, requisitions and transfers, stock takes, cost centres, budgets, charges, suppliers, purchase orders and receipts
  - [Onboarding](database/onboarding/onboarding.prisma): trusted sources, the organisations they list, collection runs, snapshots and staged records
- [Cluster](cluster.md): what Argo CD deploys from `infra/cluster/`: operators, secrets from Doppler, the database and its backups, `cloudflared` and Odoo
- [Provisioning](provisioning.md): what Ansible in `infra/ansible/` installs on a node, k3s and Argo CD, how it leaves other programs alone, and how `cd-ansible` runs it
- [Pipelines](pipelines.md): what each GitHub Actions workflow does, images, artifacts and caches
- [Secrets](secrets.md): Doppler config and the secrets published to GitHub
- [Terraform](terraform.md): what `infra/` creates in Cloudflare and GitHub
