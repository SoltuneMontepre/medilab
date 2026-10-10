# Security

What each role may do. Roles and their permissions are defined by administrators (see [People and signing](../functional/laboratory_module/features/admin.md#4-people-and-signing-us-ad13-to-us-ad16)); these documents state the permissions each role is set up with.

## Global rules

Rules that hold for everyone, whatever their roles and permissions:

- A signed document cannot be edited, archived or deleted ([SH-07](../functional/shared.md#sh-07-signed-documents-are-locked)).
- Signatures, results, people who have signed a document, test parameters, their parameter and method pairs and subcontractors are never deleted. Audit entries are never deleted by anyone; only the cleanup job removes them after the audit retention period.
- Permissions are enforced in the API and in the interface; a person does not see menus, records, fields or buttons for what they are not allowed to do.

## Permissions

A permission is an action on a document type: read, create, edit, archive, delete or sign, on every record, only those of the person's department or only those of the person's team. A role is a set of permissions. A person holds roles and can be given extra permissions directly. The administrator role is the exception: it holds every permission.

Odoo enforces permissions: each permission becomes Odoo groups, access rules and record rules, so the API and the interface follow it. Only administrators assign roles and permissions. [Permissions](../specs/permissions.md) specifies the mechanism.

One document per role, in `permissions/<role>.md`.

- [Administrator](permissions/admin.md): every permission, as Odoo's default administrator

## Related documents

- [Permissions](../specs/permissions.md)
- [Approval and signing chain](../business/approval-and-signing-chain.md)
- [Laboratory overview](../functional/laboratory_module/overview.md)
