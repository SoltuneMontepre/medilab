# Testing

How tests are written, where they live and how they run.

## Layers

| Layer         | Tool                                             | Location                              | Command               |
| ------------- | ------------------------------------------------ | ------------------------------------- | --------------------- |
| Odoo modules  | Odoo test runner (`TransactionCase`, `HttpCase`) | `src/core/modules/<module>/tests/`    | `task test:core`      |
| Browser       | Cypress                                          | `src/tests/cypress/e2e/`              | `task test:e2e`       |
| Applications  | `bun test` and `cargo test`                      | next to the code, in each application | `task test:apps`      |
| Type checking | `unittest` and pyright                           | `tools/typecheck/`                    | `task test:typecheck` |
| AI tooling    | pytest, MCP and official OdooLS                  | `tools/odoo-intelligence/tests/`      | `task ai:test`        |

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
- `test_link_addons.py` runs the linking in a temporary folder. It checks that owned links stay as they are, links to a moved, removed or new module are updated, matching unowned links remain unmanaged, other links and all real folders are kept, and the linked folders never change. A record cannot name a link outside `odoo/addons`.
- `test_pyright_report.py` feeds `typecheck.py` controlled pyright results: failed runs, invalid or incomplete reports, inconsistent diagnostic counts and runs that checked no files must fail. Startup and output-decoding failures must produce exit code 2 and an explanation.
- The `ci-core` tooling job runs these safety tests on Linux and Windows. Windows exercises real junction creation, replacement and cleanup, including preservation of target files and unmanaged junctions.

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

## AI tooling

`task ai:test` runs the tooling suite and lint checks; `ci-ai` runs it on pull requests that change the AI tooling. Live OdooLS tests run when `task ai:setup` has installed the binary and source; otherwise they report skips, as they do in CI. `task ai:verify` checks the Python and XML model and field definitions in `odoo_intelligence/navigation_cases.json` through MCP, plus completion, hover, references and symbols. [Odoo intelligence](../workflows/odoo-intelligence.md) explains the client and Cursor extension-host checks. These checks do not install application modules or alter a database.

## Related documents

- [Pipelines](../infrastructure/pipelines.md)
- [Python](python.md)
- [Taskfiles](taskfiles.md)
