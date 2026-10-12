---
name: review-pr
description: Review a MediLab pull request against the docs conventions, the business rules and the live database schema, then post the findings as one review. Reads the docs conventions first, checks the pull request out, upgrades the local database and checks the schema. Use when the user runs /review-pr or asks to review, check or comment on a pull request or PR.
---

# Review pull request

Follow [.agent/skills/review-pr/SKILL.md](../../../.agent/skills/review-pr/SKILL.md).

In Claude Code:

- Read the schema with the `postgres` MCP server; when it is not connected, say so and use `docker exec medilab-postgres psql`.
- Ask the owner the open rule questions with AskUserQuestion before drafting the review.
