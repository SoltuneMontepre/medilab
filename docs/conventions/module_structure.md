# Module structure conventions

How code inside an Odoo module is laid out.

## Group by concern

- A model and its views live in folders of the same name, for example `models/master_data/test_parameter.py` and `views/master_data/test_parameter_views.xml`.
- Folder names are snake_case, because model folders are Python packages.
- A new concern adds a folder in both `models/` and `views/` and a row to this table.
- Mixins that models of several concerns inherit, such as the permission mixin, live in `models/mixins/`, which has no views. `models/__init__.py` imports it before the concerns, because Odoo registers models in the order their classes are defined.
- Extensions of system models, such as job handlers, live in `models/system/`.

| Concern             | Contains                                                                                                                                                                         |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `master_data`       | What the laboratory can test and with what: parameters, groups, sample types, methods, units, regulations, quality registrations, machines, chemicals, subcontractors, customers |
| `sample_collection` | Test requests and samples: reception, handover, recollection, subcontract dispatches, and creating a sample's laboratory folders                                                  |
| `testing`           | Sample tests, results, machine bookings, test reports, change requests                                                                                                           |
| `tasks`             | Task types and tasks                                                                                                                                                             |
| `notifications`     | Notification events, preferences, recipients and push deliveries                                                                                                                 |
| `management`        | Features only managers use                                                                                                                                                       |
| `pricing`           | Parameter prices, taxes and their rates, subcontract costs and service packages                                                                                                  |
| `orders`            | Sale orders, the portal cart and cancellation requests                                                                                                                           |
| `support`           | Support requests and the customers' feedback on orders                                                                                                                           |
| `system`            | People, departments, roles, permissions, approval chains, signatures, the audit trail, mobile devices and menus                                                                  |
| `signing`           | Digital signing: the laboratory's signing certificates, digital signatures, their jobs and the verification page                                                                 |
| `laboratory_files`  | Laboratory folders, their members and sync rules, and the computers signed in to them                                                                                            |
| `stores`            | Stores and the locations inside them, with their holders and managers                                                                                                            |
| `costs`             | Cost centres                                                                                                                                                                     |
| `catalog`           | Stock items with their minimum quantities, suppliers and the items they sell, and how much of each item a test uses                                                              |
| `purchasing`        | Purchase orders, their lines and signing, and receipts with what each lot line brings in                                                                                         |
| `stock`             | Lots and containers, their statuses and QR labels                                                                                                                                |
| `recipes`           | Recipes of prepared solutions and their ingredients                                                                                                                              |

## Files

- One model per file, named after the model: `test_parameter.py`. An extension of an Odoo model is named after the Odoo model and lives in the folder of its MediLab concern, such as `models/system/hr_department.py` for departments and `models/tasks/calendar_event.py` for schedules.
- Views of a model go in `<model>_views.xml`.
- Abstract models that models of several concerns inherit, such as `medilab.permission.mixin`, live in `models/mixins/`, which is imported before the concerns.
- Every window action that opens a page has a `path`: the plural of the record name in lowercase with hyphens, such as `test-parameters`, so addresses read `/odoo/test-parameters/1`. A path another module already uses takes the prefix `lab-`.
- Menus are defined only in `views/system/menus.xml` and loaded last in `__manifest__.py`, after the actions they open.
- The look of the system lives in its own module, `sol_theme`, under `static/src/`, split into `scss/`, `js/`, `xml/` and `img/`. No other module refers to its assets, so every module works with Odoo's own look.
- A view type the module adds lives in `static/src/views/<view>/`, such as the timeline in `static/src/views/timeline/`; a screen of a concern lives in `static/src/<concern>/<screen>/`, such as `static/src/tasks/dashboard/`.

## Permissions

- Each new document model inherits `medilab.permission.mixin` and ships its permissions in its module's `data/permission_data.xml`: one per action in its `_permission_actions`, with scope `all`, the same actions with scope `own_department` only when the model has `department_id`, and with scope `own_team` only when it has `team_id`. A test fails when one is missing.
- Each new document model also inherits `medilab.audit.mixin` and names the documents under it in `_audit_children`, such as `sample_ids` on a test request. An Odoo model a module extends gets the mixin with `_name` set and the mixin before the Odoo name in `_inherit`, so the entry includes what Odoo's own `write` changes, such as an employee's version: `_name = MODEL_EMPLOYEE` and `_inherit = [MODEL_AUDIT_MIXIN, MODEL_EMPLOYEE]`. A model that gets the audit mixin through another mixin, such as `sale.order` through the approval mixin, lists that mixin after the Odoo name, as Python cannot order the two otherwise. A test fails when a model is left out; [Audit trail](../specs/audit-trail.md) lists the models that are.
- Permissions, the administrator role and the administrator person are shipped data. Departments, people and other roles are user data. Demo data lives only in the `sol_demo` module, which assigns shipped permissions and never creates one.
- [Permissions](../specs/permissions.md) describes the mechanism.

## Constants

Technical names used in Python live in the `constants/` package at the root of the module, one file per kind:

| File                       | Contains                                                                                    |
| -------------------------- | ------------------------------------------------------------------------------------------- |
| `constants/models.py`      | Database model names, such as `MODEL_TEST_PARAMETER`                                        |
| `constants/permissions.py` | Actions, scopes and access domains of permissions, such as `SCOPE_DOMAINS`                  |
| `constants/departments.py` | Domains that tell departments from teams, such as `DEPARTMENT_DOMAIN`                       |
| `constants/xml_ids.py`     | External ids Python code refers to, such as `ADMINISTRATOR_ROLE`                            |
| `constants/settings.py`    | System parameter keys and their defaults, such as `SAFETY_MARGIN_PARAMETER`                 |
| `constants/tasks.py`       | Task triggers and statuses, such as `MANUAL_TRIGGER`                                        |
| `constants/approvals.py`   | Approval chain purposes, signature decisions and approval states, such as `DECISION_SIGNED` |
| `constants/customers.py`   | Customer types and sign-up values, such as `SIGNUP_CUSTOMER_KEY`                            |
| `constants/audit.py`       | How the audit trail masks values, such as `MASK_PERSONAL`                                   |
| `constants/jobs.py`        | Context keys of scheduled jobs and what the cleanup job removes, such as `CLEANUP_KINDS`    |
| `constants/locks.py`       | The bus notification and release reasons of document locks, such as `LOCK_BUS_TYPE`         |
| `constants/routes.py`      | Route options that `odoo.http` does not declare, such as `FRONTEND_PAGE`                    |
| `constants/stock.py`       | Statuses of lots and containers and the Odoo states receipts rely on, such as `CONTAINER_SEALED` |
| `constants/signing.py`     | Digital signing jobs, certificate statuses, contexts and paths, such as `DIGITAL_SIGNING_JOB` |
| `constants/items.py`       | Kinds of stock items and how they are tracked, such as `KIND_SOLUTION`                      |
| `constants/laboratory_files.py` | Member roles, sync modes and access levels of laboratory folders and files, the sources of file versions, Office extensions, and the codes of their refusals, such as `FOLDER_SHARE` |
| `constants/laboratory_editing.py` | Statuses of online editing sessions, the files edited online, the editing service's address and the codes of their refusals, such as `OPEN_STATUSES` |

- Names are UPPER*SNAKE_CASE; a model constant is `MODEL*<NAME>`and holds the value of`\_name`.
- Python code refers to a model by its constant, never by repeating the string: `_name = MODEL_TEST_PARAMETER`, `self.env[MODEL_TEST_PARAMETER]`.
- XML, CSV and other non-Python files cannot import constants and keep the literal name.
- A module only shares its own constants and its dependencies' constants;
- A new kind of constant adds a file to `constants/` and a row to this table.

## Related documents

- [Translation and menus](translation.md)
- [Database models](database.md)
- [Permissions](../specs/permissions.md)
