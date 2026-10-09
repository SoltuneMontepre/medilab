# Python conventions

How Python code in the Odoo modules is written. Ruff enforces formatting and most rules from `src/core/pyproject.toml`; the rules below are the ones it cannot check.

## Tooling

| Tool        | Purpose                                     | Config                    |
| ----------- | ------------------------------------------- | ------------------------- |
| uv          | Dependencies, lock file, virtual environment | `src/core/pyproject.toml` |
| Ruff        | Formatting and linting                      | `src/core/pyproject.toml` |
| pylint-odoo | Odoo-specific checks                        | `src/core/.pylintrc`      |
| Pyright     | Type checking, `basic` mode                 | `pyrightconfig.json`      |

- Runtime packages go in `[project.dependencies]`, developer tools in the `dev` dependency group; `uv.lock` pins every version and is committed.
- `task dev:setup` creates `src/core/.venv`; `task lint`, `task format` and `task typecheck` run the tools through `uv run`.

- Python 3.12, 4-space indentation, double quotes, LF line endings, lines up to 120 characters.
- Do not silence a rule inline to make code pass; fix the code or raise the rule with the owner.

## File structure

How a module is laid out, from its root:

```text
<module>/
├── __init__.py          imports controllers and models
├── __manifest__.py
├── constants/           technical names, see Constants
├── controllers/         HTTP routes
├── models/<concern>/    one model per file
├── services/            logic that belongs to no single model
├── security/
├── data/
├── views/<concern>/
└── static/
```

- Models, views and the concern folders are described in [Module structure](module_structure.md); models themselves in [Database](database.md).
- Every folder with Python files is a package with an `__init__.py`. The `__init__.py` only imports; it holds no logic.
- `__init__.py` imports the sub-packages or files in alphabetical order: `from . import management, sample_collection, system`.
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

## Related documents

- [Module structure](module_structure.md)
- [Database](database.md)
- [Translation and menus](translation.md)
