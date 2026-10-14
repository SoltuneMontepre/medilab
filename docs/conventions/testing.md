# Testing

How tests are written, where they live and how they run.

## Layers

| Layer         | Tool                                             | Location                              | Command               |
| ------------- | ------------------------------------------------ | ------------------------------------- | --------------------- |
| Odoo modules  | Odoo test runner (`TransactionCase`, `HttpCase`) | `src/core/modules/<module>/tests/`    | `task test:core`      |
| Browser       | Cypress                                          | `src/tests/cypress/e2e/`              | `task test:e2e`       |
| Applications  | `bun test` and `cargo test`                      | next to the code, in each application | `task test:apps`      |
| Type checking | `unittest` and pyright                           | `tools/typecheck/`                    | `task test:typecheck` |

`task test` runs the module and application tests. Browser tests run against the running app, so start it first with `task up`.

## Odoo module tests

- Odoo only finds tests in the module's own `tests/` package. Its `__init__.py` imports every test file.
- One test class per file, named after the file: `test_parameter_constraints.py` holds `TestParameterConstraints`.
- Tag each class `@tagged("post_install", "-at_install")`.
- Use `TransactionCase` for models and `HttpCase` for routes.
- `task test:core` installs the modules in a throwaway database, runs only their tests with `--test-tags /<module>`, and drops the database afterwards. `task test:core MODULES=a,b` limits it to those modules; by default it runs every module in `src/core/modules.txt`.
- `task test:uninstall` installs Laboratory, E-commerce and Inventory in a throwaway database, uninstalls E-commerce and Inventory, and checks that the Laboratory data is intact.
- `task test:core` also writes the coverage report `src/core/modules/coverage.xml`, which is not committed.

## Type checking tests

- `task test:typecheck` checks that every module is linked into the Odoo source and that an import of a module's constant resolves.
- It checks that a missing name, a missing module, a type error and a wrong call fail, and that the Odoo patterns behind the [relaxed rules](python.md#relaxed-rules) pass.
- Each case is a file the test writes to a temporary folder, so no failing code is committed.
- `test_link_addons.py` runs the linking in a temporary folder. It checks that correct links stay as they are, links to a moved, removed or new module are updated, other links and folders are kept, and the linked folders never change.
- `test_pyright_report.py` feeds `typecheck.py` made-up pyright results: a failed run, an incomplete report and a run that checked no files must fail.
- The Windows junction calls are tested with mocks; the pipeline runs on Linux only.

## Pipeline

[Pipelines](../infrastructure/pipelines.md) describes how `ci-core` runs the module tests and reports coverage. Locally, `task test:core` uses the stock Odoo image unless `MEDILAB_ODOO_IMAGE` names another.

## Browser tests

- A test file is named `<feature>.cy.js` under `src/tests/cypress/e2e/`.
- Tests use the app address `MEDILAB_URL`, default `http://localhost:8069`.
- Tests do not depend on data a previous test created.
- The task unsets `ELECTRON_RUN_AS_NODE`, which editors such as VS Code set and which stops Cypress from starting.

## Applications

- Frontend tests are `*.test.ts` and `*.test.tsx` files next to the code they test, run by `bun test`.
- Rust tests run with `cargo test` when `cargo` is installed; `task test:apps` skips them with a message otherwise.

## Related documents

- [Pipelines](../infrastructure/pipelines.md)
- [Python](python.md)
- [Taskfiles](taskfiles.md)
