# Database conventions

How database models are defined in the Odoo ORM. For where model files live, see [Module structure](module_structure.md).

Code-first: changes and updates are available later.

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
- Odoo adds the primary key `id`, and `create_uid`, `create_date`, `write_uid` and `write_date`; do not declare them, and do not add a field that only repeats when or by whom a record was created.
- Measured values, limits, factors and money are numeric (`fields.Float` with digits, or `fields.Monetary`), never stored where floating point can round them; a measured value keeps how many decimals it shows.
- A field searched with "contains", such as a catalog name, gets `index="trigram"`.
- Use what the Odoo apps give before adding a table: [Module boundaries](../business/module-boundaries.md#odoo-apps) lists the app model each concept is built on, such as `hr.employee` for people, `calendar.event` for schedules and `stock.lot` for lots. From `base`: `res.partner` for contacts and tax IDs, `res.users` for logins, settings fields for system parameters, `ir.cron` for schedules, `ir.sequence` for numbers, `ir.attachment` for files, `res.currency` for money.
- A model that extends an Odoo model uses `_inherit` with the Odoo name and no `_name`; its class is named after the Odoo model, such as `HrEmployee` in `hr_employee.py`, and its added fields follow the rules below.
- Every model class has a comment on the line above it with its Vietnamese term from the [glossary](../glossaries.md). A model that only links two others says what the link is for:

  ```python
  # Chỉ Tiêu
  class TestParameter(models.Model):
  ```

  ```python
  # Links parameter and method pairs to the machines that can run them, with the run time.
  class ParameterMethodMachine(models.Model):
  ```

- Every field has a comment on the line above it saying what data it holds, including relational fields:

  ```python
  # Unique code staff and documents use for the parameter; filled from a sequence when left empty.
  code = fields.Char(required=True)
  # The group revenue reports count the parameter under; one of the parameter's groups.
  main_group_id = fields.Many2one(MODEL_PARAMETER_GROUP, required=True)
  ```

- The same applies to the [database diagrams](../infrastructure/readme.md), with a `///` comment above every field.
- Each module has its own diagram in `docs/infrastructure/database/<module>/<module>.prisma`, in its own folder. A table another module or an Odoo app owns appears only with the columns the module uses and the columns it adds, named by its Odoo table, such as `hr_employee`.
- A module adds columns to an Odoo app's table when the data belongs to that concept, such as the roles of a person on `hr_employee`. It keeps its data in its own tables rather than adding columns to tables of another MediLab module.
- Terms from the business domain follow the [glossary](../glossaries.md).

## Relationships

- Use `Many2one`, `One2many` and `Many2many` to relate models.
- A `One2many` always has its `Many2one` on the other model as the inverse.
- A relationship to a model of another module is allowed only toward a module the current one depends on: an Odoo app it depends on, or Laboratory for E-commerce and Inventory. Laboratory depends on no other MediLab module.

## Constraints and indexes

- Integrity rules are declared on the model, for example the unique code of a test parameter: `models.Constraint("UNIQUE(code)", "The code of a test parameter must be unique.")`.
- Give each constraint a message a user can act on.
- Index fields that are searched or joined often.

## Related documents

- [Module structure](module_structure.md)
- [Glossary](glossary.md)
- [Translation and menus](translation.md)
- [Module boundaries](../business/module-boundaries.md)
