# Syncing the database diagram

How a module's Prisma diagram is brought in line with the tables Odoo creates. Odoo owns the schema; the diagram only draws it.

## Steps

1. **Read the conventions** before anything else: [Database](../conventions/database.md) for how diagrams are written, [Documentation](../conventions/documentation.md) and [Infrastructure](../infrastructure/readme.md) for where they live.
2. **Upgrade the local database** to the code being compared: `task upgrade`. A database that was not upgraded shows an older schema. Say in the reply that the upgrade ran, and on which branch.
3. **Read the live schema** with the `postgres` MCP, or when it is not connected with `docker compose -f tools/infrastructure/docker-compose.yml exec -T postgres psql -U root -d medilab -c "<query>"`. Query:
   - Columns: `information_schema.columns` for tables named `medilab\_%`, leaving out `create_uid`, `write_uid`, `create_date` and `write_date`.
   - Foreign keys and their delete rules: `pg_constraint` where `contype = 'f'`; `confdeltype` is `r` restrict, `c` cascade, `n` set null.
   - Check constraints: `pg_constraint` where `contype = 'c'`.
   - Indexes: `pg_indexes`, including partial and expression indexes.
   - Extensions: `pg_extension`.
4. **Compare** each table with its model in `docs/infrastructure/database/<module>/<module>.prisma`: tables, columns and whether they are optional, relations and `onDelete`, unique constraints, indexes, check constraints.
5. **Update the diagram** for every difference in a table that exists:
   - Follow [Database](../conventions/database.md#models): a `///` comment above every field and on every model.
   - Prisma cannot draw partial, expression or check constraints; state them in the model's `///` comment.
   - A table another module or an Odoo app owns is drawn with only the columns the module uses and adds, named by its Odoo table.
6. **Report what the diagram cannot fix**: a difference that comes from the code, such as a missing index, constraint or extension. Do not change the code without the owner's approval.
7. Reply with the branch, whether the upgrade ran, the differences found and fixed, and the ones left for the owner.

## Rules

- Never change the database by hand; change the model and upgrade.
- A table the documents plan but the code does not build yet stays in the diagram. Only tables that exist are compared.
- Odoo creates boolean columns nullable. The diagram draws them as it does today, with a default, and this is not a difference.
- A diagram is in sync only when the upgrade ran on the code it is compared with. Do not call it in sync otherwise.

## Related documents

- [Database](../conventions/database.md)
- [Taskfiles](../conventions/taskfiles.md)
- [Infrastructure](../infrastructure/readme.md)
