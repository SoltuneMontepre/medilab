# Infrastructure

- Database diagrams, one Prisma schema per module:
  - [Laboratory](database/laboratory/laboratory.prisma): master data, test requests, samples, results and signing
  - [E-commerce](database/ecommerce/ecommerce.prisma): prices, taxes and service packages
- [Pipelines](pipelines.md): what each GitHub Actions workflow does, images, artifacts and caches
- [Secrets](secrets.md): Doppler config and the secrets published to GitHub
