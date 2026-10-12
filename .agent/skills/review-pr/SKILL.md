---
name: review-pr
description: Review a MediLab pull request against the docs conventions, the business rules and the live database schema, then post the findings as one review. Reads the docs conventions first, checks the pull request out, upgrades the local database and checks the schema. Use for /review-pr or when asked to review, check or comment on a pull request or PR.
---

# Review pull request

Read [AGENTS.md](../../../AGENTS.md), the [docs index](../../../docs/readme.md) and the [conventions](../../../docs/conventions/readme.md) they link before doing anything else; they override anything here. Then follow [docs/workflows/reviewing-pr.md](../../../docs/workflows/reviewing-pr.md) step by step.

- Check the change against the business rules in the documents, not only against the code.
- Read the pipeline results with `gh pr checks`; do not run the test suite, the pipelines already do.
- When the change touches models, upgrade the local database and read the live schema; do not review the schema from the code alone. When the upgrade fails on records already in the local database, read the schema from a scratch database instead.
- Ask the owner, not the author, what a rule is when the documents do not say. Post findings as statements.
- Say which document needs updating and what it should say; do not edit it.
- Show the owner the findings and post the review only after they say so. Change nothing on the pull request's branch.
- Post only the findings. Reply with the review link, what was checked and what was not.
