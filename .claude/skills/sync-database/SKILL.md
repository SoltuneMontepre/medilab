---
name: sync-database
description: Bring a MediLab module's Prisma database diagram in line with the tables Odoo creates. Reads the docs conventions first, upgrades the local database, compares the live schema with the diagram and updates the diagram. Use when the user runs /sync-database or asks to sync, check or compare the database with the diagram or the Prisma files.
---

# Sync database

Follow [.agents/skills/sync-database/SKILL.md](../../../.agents/skills/sync-database/SKILL.md).

In Claude Code:

- Read the schema with the `postgres` MCP server; when it is not connected, say so and use `docker compose -f tools/infrastructure/docker-compose.yml exec -T postgres psql` instead.
