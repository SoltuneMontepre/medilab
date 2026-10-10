# Settings

Stories: SH-01, SH-02, SH-03

## Goal

Every value a laboratory may change is a system parameter with a default, declared once by the module that needs it, shown in one MediLab tab of the settings screens and changed only by administrators. Secrets never enter the database. A module can be installed and uninstalled without touching the data of the modules it depends on.

## Design

### Declaring a parameter

A parameter is a field on `res.config.settings`, declared by the module that reads it:

```python
class ResConfigSettings(models.TransientModel):
    _inherit = MODEL_RES_CONFIG_SETTINGS

    # Days a customer has to pay an invoice after it is posted.
    invoice_due_days = fields.Integer(
        config_parameter="medilab.commerce.invoice_due_days",
        default=7,
        help="Days a customer has to pay an invoice after it is posted.",
    )
```

- `config_parameter` is the key in Odoo's system parameter table (`ir.config_parameter`): `medilab.<module>.<name>`.
- `default` is the value a fresh installation uses, and the value an installation falls back to when the parameter is missing, so adding a parameter never breaks an existing installation.
- `help` is the explanation shown on the settings screen, in English in the source and in Vietnamese in `i18n/vi.po`.
- The field has a type (boolean, integer, float, char, selection, many2one); Odoo converts the stored text to it.

### Reading a parameter

Features read a parameter through the settings model, never through `ir.config_parameter` directly:

```python
days = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("invoice_due_days")
```

`_get_parameter` returns the stored value converted to the field's type, or the field's default when the parameter is missing or empty. It reads with full rights, because only administrators may read system parameters while features read them for everyone, including jobs and public pages.

### Who changes settings

Settings are changed from the settings screens by administrators: the settings model and the system parameter table are open to Odoo's settings group only, which the administrator role implies ([Permissions](permissions.md)). Anyone else gets an access error on the screen and in the API. Auditing a change belongs to the audit trail (SH-05).

A setting that changes the behaviour of existing documents applies to future documents only: a document copies the values it needs when it is created or posted.

### The settings screen

The laboratory module adds a MediLab app to Odoo's settings form, opened from System → Settings, with one block per module:

```xml
<app data-string="MediLab" string="MediLab" name="medilab" logo="/laboratory/static/src/theme/img/icons/icon-192x192.png">
    <block title="Laboratory" name="laboratory">
        <setting id="medilab_code_formats" string="Code formats" help="...">
            ...
        </setting>
    </block>
</app>
```

Another module adds its block by inheriting `laboratory.res_config_settings_view_form` and inserting inside `//app[@name='medilab']`, so the block exists only while that module is installed. Each parameter is one `<setting>` with its field.

The Laboratory block holds the code formats: a button opening the `ir.sequence` records whose code starts with `medilab.`, where the administrator changes the prefix, padding and next number of every code and document number. The parameters of a feature are declared with that feature.

### Secrets

Provider credentials and other secrets are environment variables, read by the code when it needs them and never stored, logged or shown. Locally they come from Doppler ([Secrets](../infrastructure/secrets.md)); the settings screen may say whether a credential is configured, never its value.

### Modular installation

- `laboratory` depends on `base` and `web` only; `commerce` and `inventory` depend on `laboratory` only ([Module boundaries](../business/module-boundaries.md)).
- A module keeps its data in its own tables and adds no stored column to a table of a module it depends on; `test_module_boundaries.py` fails when one does. Uninstalling `commerce` or `inventory` therefore leaves the Laboratory data intact.
- The permissions a module ships generate their group and access with `laboratory` external identifiers ([Permissions](permissions.md)); when such a module is uninstalled, its permissions delete the group and access they generated, so nothing of the module stays in the administrator role.
- `task test:uninstall` installs the three modules in a throwaway database, uninstalls `commerce` and `inventory` and checks the Laboratory records, people and logins are unchanged and nothing of the modules is left ([Testing](../conventions/testing.md)).

## Related documents

- [Shared technical features](../functional/shared.md): SH-01, SH-02, SH-03
- [Setting up a laboratory](../workflows/setting-up.md)
- [Permissions](permissions.md)
- [Secrets](../infrastructure/secrets.md)
- [Module structure](../conventions/module_structure.md)
- [Testing](../conventions/testing.md)
