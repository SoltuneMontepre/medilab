# Module structure conventions

How code inside an Odoo module is laid out.

## Group by concern

`models/` and `views/` are split into the same folders, one per concern:

| Folder               | Contains                                                         |
| -------------------- | ---------------------------------------------------------------- |
| `system/`            | Login page, favicon, users and preferences, menus                |
| `sample_collection/` | Sample collection; currently the test parameters                 |
| `management/`        | Laboratory management                                            |
| `testing/`           | Testing                                                          |
| `tasks/`             | Tasks                                                            |

- A model and its views live in folders of the same name, for example `models/sample_collection/test_parameter.py` and `views/sample_collection/test_parameter_views.xml`.
- Folder names are snake_case, because model folders are Python packages.
- Each model folder is a package with its own `__init__.py`; `models/__init__.py` imports every folder, so adding a model only touches its folder's `__init__.py`.
- An empty view folder keeps a `.gitkeep` until it has a view.
- A new concern adds a folder in both `models/` and `views/` and a row to this table.

## Files

- One model per file, named after the model: `test_parameter.py`.
- Views of a model go in `<model>_views.xml`.
- Menus are defined only in `views/system/menus.xml` and loaded last in `__manifest__.py`, after the actions they open.
- Theme assets live in `static/src/theme/`, split into `scss/`, `js/`, `xml/` and `img/`.

## Constants

Technical names used in Python live in the `constants/` package at the root of the module, one file per kind:

| File                  | Contains                                                  |
| --------------------- | --------------------------------------------------------- |
| `constants/models.py` | Database model names, such as `MODEL_TEST_PARAMETER`      |

- Names are UPPER_SNAKE_CASE; a model constant is `MODEL_<NAME>` and holds the value of `_name`.
- Python code refers to a model by its constant, never by repeating the string: `_name = MODEL_TEST_PARAMETER`, `self.env[MODEL_TEST_PARAMETER]`.
- XML, CSV and other non-Python files cannot import constants and keep the literal name.
- A module only shares its own constants. E-commerce and Inventory may import from `odoo.addons.analysis.constants`, because they depend on Analysis; Analysis never imports from them.
- A new kind of constant adds a file to `constants/` and a row to this table.

## Related documents

- [Translation and menus](translation.md)
- [Database models](database.md)
