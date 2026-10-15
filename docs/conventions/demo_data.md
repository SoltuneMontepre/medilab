# Demo data conventions

How the `sol_demo` module seeds data for demos and browser checks.

## Rules

- Every feature adds demo data to `src/core/modules/sol_demo` in the same change as the feature, so it can be shown and checked in the browser right after it is built.
- Demo data covers the feature's flows: at least one record in each status of its lifecycle, and the cases its acceptance criteria name, such as an expired lot or an overdue calibration.
- Records are realistic for a Vietnamese testing laboratory, in Vietnamese and English where the field is translatable. They never contain real customers' or people's data.
- A `demo.<role>` user exists for every role, to check that role's screens. Their password is `demo`; a deployed environment sets another one with the `MEDILAB_DEMO_PASSWORD` environment variable at install.
- Demo data creates departments, people and roles and gives them shipped permissions; it never creates a permission ([Module structure](module_structure.md#permissions)).
- `sol_demo` depends on every module it seeds data for. The other modules never depend on `sol_demo`.
- Files live in `data/<module>/<model>.xml`, where `<module>` is the module that defines the model, such as `data/sol_laboratory/test_parameter.xml`, `data/base/res_partner.xml` and `data/account/account_move.xml`. The manifest lists them in dependency order.
- A record that needs records loaded after it is completed in a later file, such as a team's lead set in `person.xml` once the people exist.
- Record XML ids are `demo_<model>_<short name>`, such as `demo_test_parameter_lead`. Records that seeding code creates in Python follow the same rule.
- Data files use `noupdate="1"`, so upgrading the module does not overwrite records changed during a demo. Function calls stay outside it, so every upgrade runs them: a seeding function, which adds only what is missing, or a call that records loaded after it need, such as flagging Odoo's stock location as the central store, because an upgrade leaves the records of other modules unchanged.

## Related documents

- [Module structure](module_structure.md)
- [Testing](testing.md)
- [Resolving an issue](../workflows/resolving-issue.md)
