# Database conventions

How database models are defined in the Odoo ORM. For where model files live, see [Module structure](module_structure.md).

## Naming

| Thing        | Form                  | Example                     |
| ------------ | --------------------- | --------------------------- |
| `_name`      | `medilab.<name>`      | `medilab.test.parameter`    |
| Class        | PascalCase            | `TestParameter`             |
| File         | snake_case            | `test_parameter.py`         |
| Field        | snake_case            | `first_name`                |
| Constant     | `MODEL_<NAME>`        | `MODEL_TEST_PARAMETER`      |

- A model's file is named after the model and holds only that model.
- The value of `_name` is defined once, as a `MODEL_<NAME>` constant in `constants/models.py` of the module. Python code uses the constant, never the repeated string: `_name = MODEL_TEST_PARAMETER`, `self.env[MODEL_TEST_PARAMETER]`. See [Constants](module_structure.md#constants).

## Models

- Every model is defined in the `models/` folder of its module, in the folder of its concern.
- A model inherits from `models.Model`; data that is never stored uses `models.TransientModel`.
- Every model sets `_description`, a short human-readable name.
- Set `_order` when records are normally listed in a fixed order.
- Each field uses the field type that matches its data (`fields.Char`, `fields.Integer`, `fields.Datetime`, and so on).
- Odoo adds the primary key `id`; do not declare it.
- Terms from the business domain follow the [glossary](../glossaries.md).

## Relationships

- Use `Many2one`, `One2many` and `Many2many` to relate models.
- A `One2many` always has its `Many2one` on the other model as the inverse.
- A relationship to a model of another module is allowed only toward a module the current one depends on; Laboratory depends on no other module.

## Constraints and indexes

- Integrity rules are declared on the model, for example the unique code of a test parameter: `models.Constraint("UNIQUE(code)", "The code of a test parameter must be unique.")`.
- Give each constraint a message a user can act on.
- Index fields that are searched or joined often.

## Related documents

- [Module structure](module_structure.md)
- [Glossary](glossary.md)
- [Translation and menus](translation.md)
