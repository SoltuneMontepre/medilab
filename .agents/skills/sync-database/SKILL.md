---
name: sync-database
description: Bring a MediLab module's Prisma database diagram in line with the tables Odoo creates. Reads the docs conventions first, upgrades the local database, compares the live schema with the diagram and updates the diagram. Use for /sync-database or when asked to sync, check or compare the database with the diagram or the Prisma files.
---

# Sync database

Read [AGENTS.md](../../../AGENTS.md), the [docs index](../../../docs/readme.md) and the [conventions](../../../docs/conventions/readme.md) they link before doing anything else; they override anything here. Then follow [docs/workflows/syncing-database-diagram.md](../../../docs/workflows/syncing-database-diagram.md) step by step.

- Upgrade the local database first with `task upgrade`; a database that was not upgraded shows an old schema.
- Compare only tables that exist. Planned tables stay in the diagram.
- Fix the diagram, not the code. Report differences that come from the code to the owner.
- Reply with the branch, whether the upgrade ran, and the differences found, fixed and left.
