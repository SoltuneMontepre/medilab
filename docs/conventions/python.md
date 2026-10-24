# Python conventions

How Python code in the Odoo modules is written. Ruff enforces formatting and most rules from `src/core/pyproject.toml`; the rules below are the ones it cannot check.

## Tooling

| Tool        | Purpose                                      | Config                                   |
| ----------- | -------------------------------------------- | ---------------------------------------- |
| uv          | Dependencies, lock file, virtual environment | `src/core/pyproject.toml`                |
| Ruff        | Formatting and linting                       | `src/core/pyproject.toml`                |
| pylint-odoo | Odoo-specific checks                         | `src/core/.pylintrc`                     |
| Pyright     | Type checking, `basic` mode                  | `pyrightconfig.json`, `tools/typecheck/` |
| OdooLS      | Odoo model and field navigation              | `odools.toml`                            |

- Runtime packages go in `[project.dependencies]`, developer tools in the `dev` dependency group; `uv.lock` pins every version and is committed.
- `task dev:setup` creates `src/core/.venv`; `task lint`, `task format` and `task typecheck` run the tools through `uv run`.
- The AI tooling in `tools/odoo-intelligence` has its own Python 3.13 environment, `pyproject.toml` and `uv.lock`; see [Odoo intelligence](../workflows/odoo-intelligence.md).

- Python 3.12, 4-space indentation, double quotes, LF line endings, lines up to 120 characters.
- Do not silence a rule inline to make code pass; fix the code or raise the rule with the owner.

## File structure

How a module is laid out, from its root:

```text
<module>/
├── __init__.py          imports controllers, fields and models
├── __manifest__.py
├── constants/           technical names, see Constants
├── controllers/         HTTP routes
├── fields/              field types Odoo does not have, such as a 64-bit integer
├── models/<concern>/    one model per file
├── services/            logic that belongs to no single model
├── security/
├── data/
├── views/<concern>/
└── static/
```

- Models, views and the concern folders are described in [Module structure](module_structure.md); models themselves in [Database](database.md).
- Every folder with Python files is a package with an `__init__.py`. The `__init__.py` only imports; it holds no logic.
- `__init__.py` imports the sub-packages or files in alphabetical order: `from . import management, master_data, sample_collection`.
- One class per file, named after its file: `test_parameter.py` holds `TestParameter`. A controller file holds one controller class, for example `webmanifest.py` holds `MedilabWebManifest`.
- A new Python folder is added to the `__init__.py` of its parent, otherwise Odoo does not load it.

## Imports

- Order: standard library, `odoo`, then `odoo.addons`, then relative imports. Ruff sorts them.
- Import `odoo.addons.<module>` by its full path, not relatively, when importing across modules or from `constants/`.
- A module imports only from itself and from modules it depends on in `__manifest__.py`.

## Naming

| Thing                | Form                       | Example                     |
| -------------------- | -------------------------- | --------------------------- |
| Module, folder, file | snake_case                 | `sample_collection`         |
| Class                | PascalCase                 | `TestParameter`             |
| Function, variable   | snake_case                 | `get_active_parameters`     |
| Constant             | UPPER_SNAKE_CASE           | `THEME_COLOR`               |
| Private method       | leading underscore         | `_get_webmanifest`          |

- A class overriding an Odoo class that is not a model is prefixed `Medilab`, as in `MedilabWebManifest`.
- Model names, field names and the `MODEL_<NAME>` constants follow [Database](database.md).

## Constants

- A value used in more than one place, or whose meaning is not obvious from the literal, is a named constant.
- Technical names shared across files live in `constants/`; see [Module structure](module_structure.md#constants).
- A constant used by one file only is defined at the top of that file, below the imports, as `ICON_PATH` and `THEME_COLOR` are in `webmanifest.py`.

## Code

- Overriding Odoo methods: call `super()` and change the result, rather than copying the original body.
- Queries belong on the model that owns the data, as a method on it, not in controllers or views. Callers in other modules use the method through `self.env[MODEL_<NAME>]`.
- Search with `search`, `search_fetch`, `search_count` or `read_group` rather than looping over `search([])`; filter in the domain, not in Python.
- Do not run raw SQL unless the ORM cannot express the query; when you do, use parameters, never string formatting.
- Raise Odoo exceptions (`UserError`, `ValidationError`) for errors a user can act on, with a translated message.
- Comments explain why, not what, except on model classes and fields: a class names its Vietnamese term and a field says what data it holds (see [Database](database.md#models)). Do not leave commented-out code.

## Type checking

`task typecheck` runs pyright in `basic` mode on `src/core/modules` with `pyrightconfig.json`. It fails on every error and on an import of a name that a module does not define. `task test:typecheck` checks that it still does.

### Imports

- pyright finds `odoo.addons.<name>` only inside `odoo/addons` of the Odoo source. `task dev:odoo-source` links each module of `src/core/modules` there, and each Odoo addon in `ODOO_ADDONS` of `dev.taskfile.yml`: a symbolic link on Linux and macOS, a directory junction on Windows, which needs no administrator rights.
- A link shows the current code, so a changed module needs no new `task dev:odoo-source`. `task typecheck` refreshes the links first, so a new module is found too.
- `tools/typecheck/link_addons.py` records the links it makes in `.local/odoo-source/medilab-links.json` and replaces or removes only recorded links whose targets still match the record. Matching unrecorded links can be used, but remain unmanaged. Other links in `odoo/addons` stay. A conflicting unrecorded link stops it with an error naming the path. A real folder under a name it needs is deleted and linked instead only after the user confirms at the prompt; without a terminal, or on any other answer, it stops with an error naming the path, because matching files do not prove tool ownership. Invalid names in the record stop linking before any changes.
- An Odoo addon that a module imports in Python is added to `ODOO_ADDONS`.
- Import `SUPERUSER_ID` from `odoo.api`. Odoo 20 sets it on the `odoo` package only at startup, so `from odoo import SUPERUSER_ID` is a missing name to pyright.
- `lxml-stubs`, in the `dev` group, gives pyright the names of the compiled `lxml.etree`.
- `asn1crypto`, `freezegun` and `xlsxwriter`, in the `dev` group, let pyright resolve the packages that the Odoo image provides and the modules import.

### Relaxed rules

pyright cannot follow Odoo's dynamic models. These rules are warnings: the editor shows them and `task typecheck` does not fail on them.

| Rule                           | Why                                                                                                                                                                                                                                                        |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `reportAttributeAccessIssue`   | `self.env[<model>]` is typed as `BaseModel`, and fields and methods added through `_inherit` are unknown to pyright, so every field or model method access fails. `self.env.context` is typed as `frozendict`, which pyright sees without mapping methods. |
| `reportArgumentType`           | `fields.Selection(selection=...)` is typed as a sentinel, a record id as `int`, `NewId`, `str` or `False` where `Command.link()` takes an `int`, and `mapped()` returns a list or a recordset.                                                             |
| `reportOptionalContextManager` | `assertRaises` of Odoo's test cases has no annotation, so pyright infers that `with self.assertRaises(...)` may get `None`.                                                                                                                                |

- pyright reports a missing name in `from <module> import <name>` under `reportAttributeAccessIssue` too. `tools/typecheck/typecheck.py` reports those warnings as errors, so a missing name still fails.
- `typecheck.py` also fails, with exit code 2, when pyright cannot execute, exits with a code other than 0 or 1, writes no complete report, reports invalid counts or diagnostic positions, lists different diagnostic counts than its summary, or checks no files. Exit codes 0 and 1 must agree with the reported errors. Missing imported names still fail with exit code 1 when pyright reports them as warnings.
- `__manifest__.py` files are not checked: a manifest is a bare dict, which pyright reports as an unused expression.
- Every other rule keeps its `basic` level. Do not silence one with an inline comment or `cast()`; fix the code.

### Odoo typing in code

Where Odoo's annotations are narrower than its behaviour, the code says what it relies on:

- Controllers read the environment with `request_env()` from `sol_laboratory/services/request_env.py`. Odoo types `request.env` as optional, because a request may have no database.
- A route option that an addon reads, such as `website` of `http_routing`, is passed by unpacking a dict constant, because `odoo.http` does not declare it: `**FRONTEND_PAGE` from `sol_laboratory/constants/routes.py`.
- Read the context with `self.env.context.get(<key>)`. `in` and `[]` fail on its `frozendict` type.
- A Char field reads as `False` when empty, `display_name` too. Give a fallback before joining or formatting it.
- In tests, narrow an optional value with `if value is None: self.fail(...)`. pyright knows that `fail()` does not return.

## Related documents

- [Module structure](module_structure.md)
- [Database](database.md)
- [Translation and menus](translation.md)
