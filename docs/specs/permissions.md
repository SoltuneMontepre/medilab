# Permissions

Stories: US-AD01 to US-AD13, US-AD15

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

A team is a department whose parent is its department, and its manager is the team lead. A team has no teams of its own, and a department that has teams cannot become a team. A person's team must be one of the teams of their department; moving the person to another department, also from Odoo's Employees app, leaves their team. Department choices on MediLab records offer departments only, and the team choice on a person offers the teams of their department only. Odoo's Departments screen lists departments and teams together; the Teams screen of the Employees app lists the teams only.

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
| `own_department` | `[('department_id', 'in', user.employee_id.department_id.ids)]`                             |
| `own_team`       | `[('team_id', 'in', user.employee_id.person_team_id.ids)]`                                  |

The team scope goes through the person's team: `team_id` on the person, one of the teams of the person's department. Access domains are evaluated as the user from their employee, so the employee carries `person_team_id`, the team of its person, read with full rights. The own-team scope exists only for document types that have a `team_id` field, and works as the own-department scope does: a record without a team belongs to nobody's team, and a person without a team sees no record through it.

Odoo combines the accesses of the groups a user holds with "or": a person holding `person.read.all` and `person.read.own_department` reads every person. The own-department scope exists only for document types that have a `department_id` field; creating such a permission for another document type is refused. A record without a department belongs to nobody's department, so an own-department permission does not show it, and a person without a department sees no record through it.

The generated group and access carry external identifiers of the laboratory module that are not updated on upgrade:

| Object | External identifier                   | Name                 |
| ------ | ------------------------------------- | -------------------- |
| Group  | `sol_laboratory.group_permission_<code>`  | `Permission: <code>` |
| Access | `sol_laboratory.access_permission_<code>` | `Permission: <code>` |

The dots of the code become underscores in the identifier. Because the identifiers are stable, views refer to a permission's group as any other group: a field or button with `groups="sol_laboratory.group_permission_person_sign_all"` is removed from the view for everyone else.

Every feature declares the permissions of its document types in its module's `data/permission_data.xml`: `read`, `create`, `edit` and `delete` for every document type, `archive` for a type that can be archived, `sign` for a type that is signed, each with scope `all`, the same actions with scope `own_department` for a type that has a department, and with scope `own_team` for a type that has a team. A document type lists the actions it has permissions for in `_permission_actions`, and a test walks every model that inherits the shared mixin below and fails when one of those actions has no scope-`all` permission, so a feature cannot lock the administrator out of a new document type.

The permission catalogue belongs to the modules: users read permissions, rename them and give them to roles and people, but never create or delete them on the screen, so the permission document type has only the `read` and `edit` permissions. A permission a module no longer needs is deleted by that module, and its access and group go with it, unless another access still uses its group, in which case the refusal names that access.

Task types come with the modules in the same way: every internal user reads them, and only `edit` is a permission, for their route, role and default deadline. Tasks add two accesses that no permission carries: every internal user reads the tasks assigned to them and the open tasks of the queues they can claim from ([SH-10](../functional/shared.md#sh-10-tasks-and-to-do-list)). Claiming, starting and finishing their own tasks go through the task's buttons, which check the person and write with full rights.

Change requests have only the `read` and `sign` permissions, for the people who approve them. Whoever may edit a document type raises change requests on it: raising checks the `edit` permission on the document and creates the request with full rights. Change requests add one access that no permission carries: every internal user reads the change requests they raised, to follow their status.

Subcontract dispatches add one access that no permission carries: every internal user reads the dispatches they carry as sample delivery staff. A subcontractor's people are portal users and hold no permission: the portal pages read the sent and received dispatches of their subcontractor with full rights, show the samples by lab code, sample type and parameter only, and enter the results of their outsourced tests.

Master data is read the same way: every internal user reads it, because test requests, samples and tasks show it to everyone who works for the laboratory. Its other actions are permissions, given to roles and people like any other. Test parameters, ways of testing and subcontractors have no `delete` permission, since they are archived, never deleted; a way of testing refuses deleting even with full rights, and only uninstalling the module removes it. The Ways of Testing list on the parameter form archives and restores a pair through its Active toggle. Machine services, machines of ways of testing, regulation limits and testing method steps have no `archive`, since they cannot be archived. A way of testing names the department that tests it in-house, or a subcontractor, and always one of the two, so its permissions also come with scope `own_department`. A subcontractor's name, tax ID, address, phone and email are held by its company contact, which only Odoo's contact managers may create or change; the subcontractor's `create` and `edit` permissions cover them, so they are written with full rights once the subcontractor's own permission is checked, and Odoo's rule that a record needs the same rights on the contact it delegates to does not apply to subcontractors. Linking a subcontractor to an existing contact needs the right to edit that contact. Customers work the same way: their `create` and `edit` permissions cover the customer's contact, its people and its logo.

Suppliers follow the same rule: a supplier's contact details are written with full rights once its own permission is checked. Stock items and suppliers have no `delete` permission, since they are archived, never deleted; Odoo's product managers cannot delete a stock item either. A stock item is an Odoo product, which Odoo lets only its product managers create or change. So an item and its template are created, changed and archived with full rights once the item's own permission is checked. Its minimum quantities, supplier items and use per test are written as the user, so their own permissions apply. Products that are not stock items, such as the ones E-commerce sells, keep Odoo's rights.

Purchase orders, receipts and lots are Odoo's records, which Odoo lets only its purchase and stock users change. Their document types are `purchase_order`, which is signed and has a department, so it also has the `sign` action and the own-department scope; `receipt`, on Odoo's pickings, whose generated accesses are narrowed to receipts because pickings also hold other operations; and `lot`, with `edit` only, because receipts create lots and every internal user reads them, as they read containers. Every internal user reads the lines, receipts and moves of the orders they can read, as the order's screen shows them, and the moves of a receipt follow the receipt. Odoo's lot form counts the orders and transfers of a lot; a count of documents the user cannot read is left out of it. Sending an order and validating a receipt make Odoo's receipts, moves, lots, containers and stock, so they run with full rights once the order's or the receipt's `edit` permission is checked. Administrators also hold Odoo's Inventory and Purchase manager groups, to configure warehouses and operation types, and every internal user holds Odoo's lots and storage locations groups, so receipts show each line's lot and the location it goes to.

Containers, preparations and moves follow the same split. `container` has `edit` only, because every internal user already reads containers; opening a bottle and marking it empty check that edit permission, then write with full rights. Recording an opening a tester could not make checks the same permission and that the person manages the container's store or a store above it. `preparation` has `create` only, and every internal user reads preparations. `move` has `read` and `create`. The create access is narrowed to consumption, waste, relocation, adjustment and disposal, so it cannot create a receipt. There is no `move.edit`: a done move is never changed. Creating a use, a waste or a preparation checks `move.create` or `preparation.create`, and the first signature of an in-house result checks the result's own sign permission; the moves are then written with full rights, the same way a receipt is validated. Moving stock inside a store, correcting a quantity and disposing of expired stock check `move.create` and that the store is one the person keeps: a store they manage or a store under it; administrators keep every store. `stock`, on Odoo's quants, has `read` only: it opens the Stock on Hand and Expiring Soon screens of the stores the person keeps or their team or department holds, and shows the value of stock, which Odoo otherwise shows only to its stock managers. Quants change only through moves, so their other actions keep Odoo's own accesses. Every internal user also reads a move of a result they can read, a move of a preparation, and a move whose line touches a container. The scrap reason tags are read by every internal user, because recording waste asks for one. The containers scanned for a result follow the result: whoever reads the result reads them, and whoever may edit it changes them while it is a draft.

The Odoo apps MediLab builds on ship groups of their own, such as the employee and calendar managers. MediLab users get access through permissions only; the apps' own groups are given to administrators through the administrator role. One access of an app stays for everyone: Odoo's `hr` app lets every internal user read every department, which its Directory needs. Odoo shows its Departments menu only to employee officers and department managers, listing the departments they manage; the department read permission shows the menu with every department. Creating, editing, archiving and deleting departments still take their permissions, also for a department's manager.

A permission is refused when its document type does not list its action in `_permission_actions`, when it is `archive` on a document type that cannot be archived, or when its document type does not inherit the shared mixin, since only the mixin tells editing from archiving.

### Role

A role holds permissions. Creating a role creates its group, `sol_laboratory.group_role_<code>`, named `Role: <code>`; changing the role's permissions replaces the group's implied groups by the groups of those permissions; deleting the role deletes the group. A role code is lowercase letters, digits and underscores, starting with a letter, and cannot change once the role exists, because it names the role's group; the name can change.

The **administrator** role ships with the module. Its group, `sol_laboratory.group_role_administrator`, implies Odoo's settings group and the manager group of Odoo's Employees app, so a person holding the role also configures Odoo and manages its employees. Every permission a module creates is added to the administrator role, so its group implies every permission group, including those of features added later. The role cannot be deleted or renamed, and no permission can be removed from it.

The administrator person delegates to the employee of Odoo's default administrator, the user created with the database: the employee Odoo's demo data gives that user, or otherwise one the module creates. They hold the administrator role, and they cannot be archived or deleted, lose the role or be given another user, also from Odoo's Employees app.

### Person

A person delegates to an Odoo employee, so the person form shows and writes the employee's fields. Their details are the employee's work contact, which Odoo's `hr` app keeps; their login is the employee's Odoo user. A person created for a user who already has an employee delegates to that employee. When a person is saved with a login and has no user yet, the Odoo user is created as an internal user and linked to the employee. A login belongs to one person, and the login of a person who signs in cannot be emptied; the person is archived instead. Passwords are set by Odoo administrators from the user form, which the person form opens.

The effective permissions of a person are those of their roles plus their direct permissions. Whenever a person is created, changes roles, direct permissions or user, or is deleted, including when an administrator changes or deletes their employee in Odoo's Employees app, the Odoo user's groups are set to the internal user group, the groups of the person's roles and the groups of their direct permissions. Only groups that belong to a role or a permission are added or removed; any other group of the user is left as it is. The synchronisation runs with full rights, because the authorisation that matters is the permission on the person record itself.

Only administrators grant access: the person's user, login, roles and direct permissions, and a role's permissions, are limited to the administrator group, so they are neither shown to nor writable by anyone else. Without this, a person allowed to edit people could move their user onto a person with stronger roles. Who holds a role or a permission is set from the person, and a role's permissions from the role; the reverse links on roles and permissions are read-only, because only the person and the role keep the users' groups in sync.

A person editor changes a person's details on the employee; Odoo's `hr` app writes the email and phone to the work contact, and the module writes the name, also when the employee is renamed in Odoo's Employees app. Linking an employee to another user or contact is limited to administrators, so a person editor cannot change the details of someone else's contact.

Archiving a person archives their Odoo user and employee, so they can no longer sign in and leave Odoo's Employees app; unarchiving the person restores both, and archiving the employee in Odoo's Employees app archives the person. Deleting a person keeps their employee; deleting an employee deletes its person first, which takes the permission to delete the person.

### Enforcement in the API

Accesses enforce `read`, `create` and `delete`, and their domain limits `create` to the person's department when that is the scope. `edit` and `archive` share Odoo's write operation, so the shared mixin `medilab.permission.mixin`, inherited by departments through their Odoo model, by people, by roles and permissions, by master data and by every document model of later features, splits them:

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

Departments and people follow [Archiving and deleting](../business/archiving-and-deleting.md); roles and permissions have no archive and are deleted once nothing refers to them. A role a person holds cannot be deleted, a department that people, teams or ways of testing name cannot be archived or deleted, a team that people belong to cannot be archived or deleted, and deleting a person removes them from their roles and takes the role and permission groups off their user.

Referring records are found with full rights, so records the user cannot see still block archiving or deleting. The refusal names only the records the user can read and gives the others as a count, so it reveals no hidden record.

A way of testing names the department that tests it in-house, or a subcontractor, and always one of the two, never both.

### Shipped, user and demo data

| Data                    | Records                                                       | Who creates it                                                                                                 |
| ----------------------- | ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Shipped with the module | Permissions, the administrator role, the administrator person | The module, on every install. Users choose among them and assign them; they cannot delete them on the screen.  |
| User data               | Departments, people, roles other than the administrator       | Administrators and the people they give the permissions to.                                                    |
| Demo data               | Departments, people with their users, roles                   | Only the `sol_demo` module. It assigns shipped permissions to its roles and people and never creates a permission. |

### Lifecycle

Installing the module loads its permissions and generates their objects. Shipped permissions are loaded once and never overwritten by an upgrade, so a name an administrator changed stays; the generated objects stay as well, because their external identifiers are not updated. Uninstalling removes every record with an external identifier of the module: the accesses before the groups they refer to, then the groups.

### Document types of this feature

| Document type | Actions                             | Scopes              |
| ------------- | ----------------------------------- | ------------------- |
| Department    | read, create, edit, archive, delete | all                 |
| Person        | read, create, edit, archive, delete | all, own_department, own_team |
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
