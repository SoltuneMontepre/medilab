# Demo data conventions

How the `demo` module seeds data for demos and browser checks.

## Rules

- Every feature adds demo data to `src/core/modules/demo` in the same change as the feature, so it can be shown and checked in the browser right after it is built.
- Demo data covers the feature's flows: at least one record in each status of its lifecycle, and the cases its acceptance criteria name, such as an expired lot or an overdue calibration.
- Records are realistic for a Vietnamese testing laboratory, in Vietnamese and English where the field is translatable. They never contain real customers' or people's data.
- Demo users exist for every role, so each actor's screens can be checked. Their passwords come from the local development configuration and are never real credentials.
- `demo` depends on every module it seeds data for. The other modules never depend on `demo`.
- Files live in `data/<module>/<model>.xml`, such as `data/laboratory/test_parameter.xml`, and are listed in the manifest in dependency order.
- Record XML ids are `demo_<model>_<short name>`, such as `demo_test_parameter_lead`.
- Data files use `noupdate="1"`, so upgrading the module does not overwrite records changed during a demo.

## Related documents

- [Module structure](module_structure.md)
- [Testing](testing.md)
- [Resolving an issue](../workflows/resolving-issue.md)
