# Settings

Stories: SH-01, SH-02, SH-03

## Goal

Every value a laboratory may change is a system parameter with a default, declared once by the module that needs it, shown in that module's block of the settings screen and changed only by administrators. Secrets never enter the database. A module can be installed and uninstalled without touching the data of the modules it depends on.

## Design

### Declaring a parameter

A parameter is a field on `res.config.settings`, declared by the module that reads it. `config_parameter` is the key `sol_<module>.<name>` in Odoo's system parameter table. `default` is the value a fresh installation uses, and the value an installation falls back to when the parameter is missing. `help` is the explanation shown on the settings screen.

The Laboratory block holds the safety margin and the [audit](audit-trail.md) retention period, and opens Code formats, the `medilab.*` sequences. Each later module adds its own `<app>` block, shown only while that module is installed.

### Reading a parameter

Features read a parameter through the settings model, never through `ir.config_parameter` directly:

```python
days = self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("safety_margin_days")
```

`_get_parameter` returns the stored value converted to the field's type, or the field's default when the parameter is missing or empty. It reads with full rights, because only administrators may read system parameters while features read them for everyone, including jobs and public pages.

### Who changes settings

Settings sits under the Configuration menu of the Laboratory app, as settings do in Odoo's own apps, and opens the settings screen on the Laboratory block; Odoo's Settings app shows the same blocks. The menu is limited to Odoo's settings group. The administrator role implies that group. A setting that changes the behaviour of existing documents applies to documents created from then on; the safety margin is an example, because a sample test keeps the due date it already stored.

### Installation and removal

Laboratory installs alone. E-commerce and Inventory each depend on Laboratory and on the Odoo Community apps named in the module boundaries, and on no other MediLab module. Uninstalling E-commerce or Inventory deletes the permissions that module shipped, including the group and access each permission generated, and leaves Laboratory's records, people and logins in place. A stored column on a Laboratory table may only come from Laboratory.

## Related documents

- [Shared technical features](../functional/shared.md): SH-01, SH-02, SH-03
- [Setting up](../workflows/setting-up.md)
- [Module boundaries](../business/module-boundaries.md)
- [Permissions](permissions.md)
