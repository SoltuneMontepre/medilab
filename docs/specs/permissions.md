# Permissions

Stories: US-AD13, US-AD15

## Goal

Departments, people, roles and permissions are records administrators maintain. This spec states how those records become Odoo groups and accesses, so that the API and the interface enforce every permission without code per feature, how the administrator holds every permission, and how a permission limited to the person's department is applied.

## Design

### Records and the Odoo objects they produce

| Record       | Odoo objects                                                                                   |
| ------------ | ---------------------------------------------------------------------------------------------- |
| `Permission` | One group and one access, created with the permission and deleted with it.                     |
| `Role`       | One group whose implied groups are the groups of the role's permissions.                       |
| `Person`     | The person's Odoo user holds the groups of the person's roles and of their direct permissions. |

A department is Odoo's `hr.department`, extended by the laboratory module. A person is the module's `medilab.person`, which delegates to an Odoo employee (`hr.employee`) with `_inherits`: the person's table holds their team, roles and direct permissions, and the employee their name, user, work contact and department. Roles and permissions are the module's own models.

Odoo checks a user's groups transitively: a role group implies its permission groups, so a user holding the role group holds every access of those permissions. An access (Odoo's `ir.access`) gives its group one operation on a model, limited to the records of its domain; menus whose action model the user cannot read are hidden by Odoo. Generated groups have no privilege, so the user form shows them as independent extra rights, which matches permissions adding up.

### Permission

A permission is one action on one document type within one scope. Its code is derived from the three: the document type is the model name without `medilab.`, or, for an Odoo model, the name of its MediLab concept, such as `department` for `hr.department`. So a permission to edit people of the person's department is `person.edit.own_department`. No two permissions share the same document type, action and scope. The document type, action and scope cannot change once the permission exists; the name can.

| Action    | Operation of the access                                                 |
| --------- | ----------------------------------------------------------------------- |
| `read`    | `r`                                                                     |
| `create`  | `c`                                                                     |
| `edit`    | `u`                                                                     |
| `archive` | `u`; the shared mixin below limits it to the `active` field             |
| `delete`  | `d`                                                                     |
| `sign`    | none: the group alone marks who may sign; the signing feature checks it |

| Scope            | Domain of the access                                                                        |
| ---------------- | ------------------------------------------------------------------------------------------- |
| `all`            | every record: `[(1, '=', 1)]`                                                               |
| `own_department` | `[('department_id', '=', user.employee_id.department_id.id)]`                               |

The team scope (`own_team`) planned for teams within departments follows the same mechanism through the person's team, `team_id` on the person, a department whose parent is the person's department, and is built with teams.

Odoo combines the accesses of the groups a user holds with "or": a person holding `person.read.all` and `person.read.own_department` reads every person. The own-department scope exists only for document types that have a `department_id` field; creating such a permission for another document type is refused. A record without a department belongs to nobody's department, so an own-department permission does not show it.

The generated group and access carry external identifiers of the laboratory module that are not updated on upgrade:

| Object | External identifier                   | Name                 |
| ------ | ------------------------------------- | -------------------- |
| Group  | `sol_laboratory.group_permission_<code>`  | `Permission: <code>` |
| Access | `sol_laboratory.access_permission_<code>` | `Permission: <code>` |

The dots of the code become underscores in the identifier. Because the identifiers are stable, views refer to a permission's group as any other group: a field or button with `groups="sol_laboratory.group_permission_person_sign_all"` is removed from the view for everyone else.

Every feature declares the permissions of its document types in its module's `data/permission_data.xml`: `read`, `create`, `edit` and `delete` for every document type, `archive` for a type that can be archived, `sign` for a type that is signed, each with scope `all`, and the same actions with scope `own_department` for a type that has a department. A document type lists the actions it has permissions for in `_permission_actions`, and a test walks every model that inherits the shared mixin below and fails when one of those actions has no scope-`all` permission, so a feature cannot lock the administrator out of a new document type.

The permission catalogue belongs to the modules: users read permissions, rename them and give them to roles and people, but never create or delete them on the screen, so the permission document type has only the `read` and `edit` permissions. A permission a module no longer needs is deleted by that module, and its access and group go with it, unless another access still uses its group, in which case the refusal names that access.

Task types come with the modules in the same way: every internal user reads them, and only `edit` is a permission, for their route, role and default deadline. Tasks add two accesses that no permission carries: every internal user reads the tasks assigned to them and the open tasks of the queues they can claim from ([SH-10](../functional/shared.md#sh-10-tasks-and-to-do-list)). Claiming, starting and finishing their own tasks go through the task's buttons, which check the person and write with full rights.

The Odoo apps MediLab builds on ship groups of their own, such as the employee and calendar managers. MediLab users get access through permissions only; the apps' own groups are given to administrators through the administrator role.

A permission is refused when Odoo cannot enforce it as stated: `archive` on a document type that cannot be archived, and `edit` or `archive` on a document type that does not inherit the shared mixin, since Odoo alone cannot tell editing from archiving there. The master data of the laboratory still uses its own accesses and joins the mixin when its access moves to permissions.

### Role

A role holds permissions. Creating a role creates its group, `sol_laboratory.group_role_<code>`, named `Role: <code>`; changing the role's permissions replaces the group's implied groups by the groups of those permissions; deleting the role deletes the group. A role code is lowercase letters, digits and underscores, starting with a letter, and cannot change once the role exists, because it names the role's group; the name can change.

The **administrator** role ships with the module. Its group, `sol_laboratory.group_role_administrator`, implies Odoo's settings group, so a person holding the role also configures Odoo. Every permission a module creates is added to the administrator role, so its group implies every permission group, including those of features added later. The role cannot be deleted or renamed, and no permission can be removed from it.

The person of Odoo's default administrator, the employee Odoo's `hr` app creates for the user created with the database, belongs to the administrator person: they hold the administrator role, and they cannot be archived or deleted, lose the role or be given another user.

### Person

A person delegates to an Odoo employee, so the person form shows and writes the employee's fields. Their details are the employee's work contact, which Odoo's `hr` app keeps; their login is the employee's Odoo user. When a person is saved with a login and has no user yet, the Odoo user is created as an internal user and linked to the employee. A login belongs to one person, and the login of a person who signs in cannot be emptied; the person is archived instead. Passwords are set by Odoo administrators from the user form, which the person form opens.

The effective permissions of a person are those of their roles plus their direct permissions. Whenever a person is created, changes roles, direct permissions or user, or is deleted, the Odoo user's groups are set to the internal user group, the groups of the person's roles and the groups of their direct permissions. Only groups that belong to a role or a permission are added or removed; any other group of the user is left as it is. The synchronisation runs with full rights, because the authorisation that matters is the permission on the person record itself.

Only administrators grant access: the person's user, login, roles and direct permissions, and a role's permissions, are limited to the administrator group, so they are neither shown to nor writable by anyone else. Without this, a person allowed to edit people could move their user onto a person with stronger roles. Who holds a role or a permission is set from the person, and a role's permissions from the role; the reverse links on roles and permissions are read-only, because only the person and the role keep the users' groups in sync.

A person editor changes a person's details on the employee; Odoo's `hr` app writes them to the work contact. Linking an employee to another user or contact is limited to administrators, so a person editor cannot change the details of someone else's contact.

Archiving a person archives their Odoo user, so they can no longer sign in; unarchiving the person restores the user.

### Enforcement in the API

Accesses enforce `read`, `create` and `delete`, and their domain limits `create` to the person's department when that is the scope. `edit` and `archive` share Odoo's write operation, so the shared mixin `medilab.permission.mixin`, inherited by departments through their Odoo model, by people, by roles and permissions and by every document model of later features, splits them:

- Writing `active` needs the archive permission; writing any other field needs the edit permission.
- Each is checked against the records inside that action's scope, found from the permissions of the user's groups for the model and action, so a person with `edit` on every record and `archive` on their own department cannot archive another department's records, even though Odoo combines the two write accesses with "or".
- Without the archive permission, `active` is read-only for the user, which also keeps the interface from offering Archive. A user with `create` but without `archive` still creates records: the field keeps its default and is not written.
- The mixin offers `_has_permission(action)` and `_permission_domain(action)` to features with their own actions, such as signing.
- Permissions and roles inherit the mixin too, so their screens follow the same rules.

There is no administrator bypass in the mixin: the administrator holds every permission, and the restrictions, accesses without a group, hold for them. The signing feature (US-AD14) adds the rule that a signed document cannot be edited, archived or deleted to the same write and delete path, for everyone.

### Enforcement in the interface

| Element                         | Hidden by                                                                                     |
| ------------------------------- | --------------------------------------------------------------------------------------------- |
| Menu                            | Odoo hides a menu whose action opens a model the user cannot read.                            |
| Record                          | The domains of the accesses: it is neither listed, found by search nor opened by its address. |
| Create, Delete buttons          | The view's root attributes, which Odoo sets from the accesses.                                |
| Edit                            | The same attribute, which the mixin also sets off when the edit permission is missing.        |
| Archive                         | The Archive action appears only while `active` is writable for the user.                      |
| Field, button, other view parts | `groups="sol_laboratory.group_permission_<code>"` on the view node.                               |

### Archiving and deleting

Departments and people follow [Archiving and deleting](../business/archiving-and-deleting.md); roles and permissions have no archive and are deleted once nothing refers to them. A role a person holds cannot be deleted, a department that people or ways of testing name cannot be archived or deleted, and deleting a person removes them from their roles and takes the role and permission groups off their user.

Referring records are found with full rights, so records the user cannot see still block archiving or deleting. The refusal names only the records the user can read and gives the others as a count, so it reveals no hidden record.

A way of testing names the department that tests it in-house, or a subcontractor, never both.

### Shipped, user and demo data

| Data                    | Records                                                       | Who creates it                                                                                                 |
| ----------------------- | ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Shipped with the module | Permissions, the administrator role, the administrator person | The module, on every install. Users choose among them and assign them; they cannot delete them on the screen.  |
| User data               | Departments, people, roles other than the administrator       | Administrators and the people they give the permissions to.                                                    |
| Demo data               | Departments, people with their users, roles                   | Only the `sol_demo` module. It assigns shipped permissions to its roles and people and never creates a permission. |

The master data of the laboratory still gives its access through Odoo's settings group and the internal user group, until its access moves to permissions.

### Lifecycle

Installing the module loads its permissions and generates their objects. Shipped permissions are loaded once and never overwritten by an upgrade, so a name an administrator changed stays; the generated objects stay as well, because their external identifiers are not updated. Uninstalling removes every record with an external identifier of the module: the accesses before the groups they refer to, then the groups.

### Document types of this feature

| Document type | Actions                             | Scopes              |
| ------------- | ----------------------------------- | ------------------- |
| Department    | read, create, edit, archive, delete | all                 |
| Person        | read, create, edit, archive, delete | all, own_department |
| Role          | read, create, edit, delete          | all                 |
| Permission    | read, edit                          | all                 |

## Related documents

- [Security](../security/readme.md)
- [Administrator](../security/permissions/admin.md)
- [Laboratory administrator](../functional/laboratory_module/features/admin.md)
- [Archiving and deleting](../business/archiving-and-deleting.md)
- [Database diagram](../infrastructure/database/laboratory/laboratory.prisma)
- [Module structure](../conventions/module_structure.md)
- [Database conventions](../conventions/database.md)
