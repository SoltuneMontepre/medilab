# Testing

How tests are written, where they live and how they run.

## Layers

| Layer        | Tool                                             | Location                              | Command          |
| ------------ | ------------------------------------------------ | ------------------------------------- | ---------------- |
| Odoo modules | Odoo test runner (`TransactionCase`, `HttpCase`) | `src/core/modules/<module>/tests/`    | `task test:core` |
| Browser      | Cypress                                          | `src/tests/cypress/e2e/`         | `task test:e2e`  |
| Applications | `bun test` and `cargo test`                      | next to the code, in each application | `task test:apps` |

`task test` runs the module and application tests. Browser tests run against the running app, so start it first with `task up`.

## Odoo module tests

- Odoo only finds tests in the module's own `tests/` package. Its `__init__.py` imports every test file.
- One test class per file, named after the file: `test_parameter_constraints.py` holds `TestParameterConstraints`.
- Tag each class `@tagged("post_install", "-at_install")`.
- Use `TransactionCase` for models and `HttpCase` for routes.
- `task test:core` installs the modules in a throwaway database, runs only their tests with `--test-tags /<module>`, and drops the database afterwards. `task test:core MODULES=a,b` limits it to those modules; the default is `laboratory`.
- `task test:core` also writes the coverage report `src/core/modules/coverage.xml`, which is not committed.

## Pipeline

- The `test` job of `ci-core` runs after `build`, runs `task test:core` and uploads the coverage report. The `sonarqube` job runs after it, downloads the report and fails the pipeline when the quality gate fails, so SonarQube Cloud measures coverage of the Odoo modules.
- Static assets, the applications and the tests themselves are excluded from SonarQube coverage in `sonar-project.properties`, because no coverage report exists for them.
- Browser tests do not run in the pipeline.

## Browser tests

- A test file is named `<feature>.cy.js` under `src/tests/cypress/e2e/`.
- Tests use the app address `MEDILAB_URL`, default `http://localhost:8069`.
- Tests do not depend on data a previous test created.
- The task unsets `ELECTRON_RUN_AS_NODE`, which editors such as VS Code set and which stops Cypress from starting.

## Applications

- Frontend tests are `*.test.ts` and `*.test.tsx` files next to the code they test, run by `bun test`.
- Rust tests run with `cargo test` when `cargo` is installed; `task test:apps` skips them with a message otherwise.

## Related documents

- [Python](python.md)
- [Taskfiles](taskfiles.md)
