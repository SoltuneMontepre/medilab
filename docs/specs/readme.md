# Specs

Technical specifications of parts of the system: their design, data and behaviour.

## Writing a spec

- A feature has a spec when building it needs technical design that the functional documents do not give, such as how permissions are enforced or how the scheduler picks a slot. Features that only maintain records described by the diagram need none.
- One spec per part of the system, named after it: `<topic>.md`, such as `permissions.md`.
- A spec starts with the user story IDs it covers, then states the goal and the design. It ends with **Related documents**.

```markdown
# <Topic>

Stories: US-AD13, US-AD15

## Goal

## Design

## Related documents
```

## Specs

- [Permissions](permissions.md): how permission, role and person records become Odoo groups, access rules and record rules, and how the own-department scope is applied

## Related documents

- [Documentation conventions](../conventions/documentation.md)
