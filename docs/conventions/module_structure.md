# Module structure conventions

How code inside an Odoo module is laid out.

## Group by concern

- A model and its views live in folders of the same name, for example `models/master_data/test_parameter.py` and `views/master_data/test_parameter_views.xml`.
- Folder names are snake_case, because model folders are Python packages.
- A new concern adds a folder in both `models/` and `views/` and a row to this table.

| Concern             | Contains                                                                                                                                                                         |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `master_data`       | What the laboratory can test and with what: parameters, groups, sample types, methods, units, regulations, quality registrations, machines, chemicals, subcontractors, customers |
| `sample_collection` | Test requests and samples: reception, handover, recollection, subcontract dispatches                                                                                             |
| `testing`           | Sample tests, results, machine bookings, test reports, change requests                                                                                                           |
| `tasks`             | Task types and tasks                                                                                                                                                             |
| `management`        | Features only managers use                                                                                                                                                       |
| `system`            | People, departments, roles, permissions, approval chains, signatures, mobile devices, menus and the theme                                                                        |

## Files

- One model per file, named after the model: `test_parameter.py`.
- Views of a model go in `<model>_views.xml`.
- Menus are defined only in `views/system/menus.xml` and loaded last in `__manifest__.py`, after the actions they open.
- Theme assets live in `static/src/theme/`, split into `scss/`, `js/`, `xml/` and `img/`.

## Permissions

- Each new document model inherits `medilab.permission.mixin` and ships its permissions in its module's `data/permission_data.xml`: one per action in its `_permission_actions`, with scope `all`, and the same actions with scope `own_department` only when the model has `department_id`. A test fails when one is missing.
- Permissions, the administrator role and the administrator person are shipped data. Departments, people and other roles are user data. Demo data lives only in the `demo` module, which assigns shipped permissions and never creates one.
- [Permissions](../specs/permissions.md) describes the mechanism.

## Constants

Technical names used in Python live in the `constants/` package at the root of the module, one file per kind:

| File                       | Contains                                                                   |
| -------------------------- | -------------------------------------------------------------------------- |
| `constants/models.py`      | Database model names, such as `MODEL_TEST_PARAMETER`                       |
| `constants/permissions.py` | Actions, scopes and access domains of permissions, such as `SCOPE_DOMAINS` |
| `constants/xml_ids.py`     | External ids Python code refers to, such as `ADMINISTRATOR_ROLE`           |

- Names are UPPER*SNAKE_CASE; a model constant is `MODEL*<NAME>`and holds the value of`\_name`.
- Python code refers to a model by its constant, never by repeating the string: `_name = MODEL_TEST_PARAMETER`, `self.env[MODEL_TEST_PARAMETER]`.
- XML, CSV and other non-Python files cannot import constants and keep the literal name.
- A module only shares its own constants and its dependencies' constants;
- A new kind of constant adds a file to `constants/` and a row to this table.

## Related documents

- [Translation and menus](translation.md)
- [Database models](database.md)
- [Permissions](../specs/permissions.md)
