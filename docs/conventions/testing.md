# Testing

How tests are written, where they live and how they run.

## Layers

| Layer         | Tool                                             | Location                              | Command               |
| ------------- | ------------------------------------------------ | ------------------------------------- | --------------------- |
| Odoo modules  | Odoo test runner (`TransactionCase`, `HttpCase`) | `src/core/modules/<module>/tests/`    | `task test:core`      |
| Browser       | Cypress                                          | `src/tests/cypress/e2e/`              | `task test:e2e`       |
| Applications  | `bun test`, Jest and `cargo test`                | next to the code, in each application | `task test:apps`      |
| Type checking | `unittest` and pyright                           | `tools/typecheck/`                    | `task test:typecheck` |
| AI tooling    | pytest, MCP and official OdooLS                  | `tools/odoo-intelligence/tests/`      | `task ai:test`        |
| Taskfiles     | `unittest` and Task                             | `tools/scripts/test_taskfile_modules.py` | `task test:taskfiles` |

`task test` runs the module and application tests. Browser tests run against the running app, so start it first with `task up`.

## Odoo module tests

- Odoo only finds tests in the module's own `tests/` package. Its `__init__.py` imports every test file.
- One test class per file, named after the file: `test_parameter_constraints.py` holds `TestParameterConstraints`.
- Tag each class `@tagged("post_install", "-at_install")`.
- Use `TransactionCase` for models and `HttpCase` for routes.
- Routes of the laboratory files API are tested through `LaboratoryApiCase` (`sol_laboratory/tests/laboratory_api_case.py`), which checks every answer against the API's OpenAPI document: a documented status, its required headers, a body matching its schema and the status of a refusal's code. A route whose answer the document does not give fails its tests. Tests that call the laboratory files bucket use `LaboratoryBucketCase` (`sol_laboratory/tests/laboratory_bucket_case.py`) against the Garage server of Docker Compose, which `task test:core` sets up first; it calls presigned addresses as computers do. The reconciliation tests use a bucket of their own, `laboratory-files-reconcile`, which they empty before and after each test. Races of two real transactions use `laboratory_files_concurrency_case.py`; retries inside a request are tested by making a step fail on concurrency on its first try.
- `task test:core` uses the selected, ownership-checked Compose project. It refuses a preexisting test database, shard database or Odoo test directory, records a local test-run marker, installs the modules in that throwaway database, copies it once per shard and runs the shards at once, each with the `--test-tags /<module>:<class>` of its classes. `tools/scripts/test_shards.py` splits the classes so each shard has about the same number of test methods. The output of each shard starts with `[shard <n>]`. The task removes only its marked test databases and directory afterwards; an interrupted run with a marker requires review before another run. `MEDILAB_TEST_DB` names the test database, `medilab_test` by default; give each run its own name when two run against the same Postgres. A worktree's compose project has a Postgres of its own, so `task test:core` there leaves the main checkout's alone once the worktree has its own ports ([A second stack from a worktree](../../README.md#a-second-stack-from-a-worktree)). `task test:core MODULES=a,b` limits it to those modules; by default it runs every module in `src/core/modules.txt`.
- `task test:core RUNNER=2 RUNNERS=3` splits the classes into four shards per machine and runs the second machine's four; `ci-core` runs three machines this way. `EXCLUDE=<module>` leaves a module out, `TEST_MODULES=a,b` runs the tests of only those modules while all are installed, and `INSTALL_COVERAGE=false` installs without coverage, which is about 60% faster. With `COVERAGE_DIR=<folder>` the task saves its raw coverage data there instead of writing the report, and `task test:core:coverage COVERAGE_DIR=<folder>` combines the data of all machines into the report.
- Tests in different classes run in different processes and databases, so a test never depends on another class having run.
- `task test:uninstall` installs Laboratory, E-commerce and Inventory in a guarded throwaway database, uninstalls E-commerce and Inventory, and checks that the Laboratory data is intact. It refuses a selected fresh demo because its standalone test uses the application's filestore.
- `task test:core` also combines the coverage of the install and of every shard into the report `src/core/modules/coverage.xml`, which is not committed. Task installs its pinned Linux Python 3.12 coverage package into ignored `.local/core-test-coverage` on the host and mounts it read-only in test containers, so a container with restricted DNS can still run coverage without changing the saved application image.

## Type checking tests

- `task test:typecheck` checks that every module is linked into the Odoo source and that an import of a module's constant resolves.
- It checks that a missing name, a missing module, a type error and a wrong call fail, and that the Odoo patterns behind the [relaxed rules](python.md#relaxed-rules) pass.
- Each case is a file the test writes to a temporary folder, so no failing code is committed.
- `test_link_addons.py` runs the linking in a temporary folder. It checks that owned links stay as they are, links to a moved, removed or new module are updated, matching unowned links remain unmanaged, other links and all real folders are kept, and the linked folders never change. A record cannot name a link outside `odoo/addons`.
- `test_pyright_report.py` feeds `typecheck.py` controlled pyright results: failed runs, invalid or incomplete reports, inconsistent diagnostic counts and runs that checked no files must fail. Startup and output-decoding failures must produce exit code 2 and an explanation.
- The `ci-core` tooling job runs these safety tests on Linux and Windows. Windows exercises real junction creation, replacement and cleanup, including preservation of target files and unmanaged junctions.

## Pipeline

[Pipelines](../infrastructure/pipelines.md) describes how `ci-core` runs the module tests and reports coverage. Locally, `task test:core` uses the image `task up` builds from `tools/dockerfiles/prod.dockerfile` unless `MEDILAB_ODOO_IMAGE` names another.

## Browser tests

- A test file is named `<feature>.cy.js` under `src/tests/cypress/e2e/`.
- Every feature has a browser test of its main path, written with the feature: it signs in as the demo user of the role that does the work, such as `demo.tester`, and walks the main path on the demo data.
- A test signs in with `signIn(<login>)` and calls a model method in that session with `call(<model>, <method>, <args>)`, both from `cypress/support/odoo.js`, instead of keeping its own copy.
- Tests use the app address `MEDILAB_URL`, default `http://localhost:8069`.
- Tests do not depend on data a previous test created.
- The task unsets `ELECTRON_RUN_AS_NODE`, which editors such as VS Code set and which stops Cypress from starting.
- `task test:e2e:app` installs every module with the demo data into the app's database and starts Odoo, then waits until it answers. `ci-core` runs it before `task test:e2e`, so tests can sign in as the demo users. Locally it changes the database of `task up`; it refuses a selected fresh demo to avoid reinstalling into its completed application database.

## Applications

- Frontend tests are `*.test.ts` and `*.test.tsx` files next to the code they test, run by `bun test`.
- React Native does not run under `bun test`, so Medilab Mobile's tests run with Jest and the `jest-expo` preset through `bun run test`, and render screens with React Native Testing Library. Every file under its `src/app/` is a route, so a screen and its test live in `src/features/<area>/` and the route file only exports the screen.
- Rust tests run with `cargo test` when `cargo` is installed; `task test:apps` skips them with a message otherwise.

## AI tooling

`task ai:test` runs the tooling suite and lint checks; `ci-tools` runs it on pull requests that change the AI tooling. Live OdooLS tests run when `task ai:setup` has installed the binary and source; otherwise they report skips, as they do in CI. `task ai:verify` checks the Python and XML model and field definitions in `odoo_intelligence/navigation_cases.json` through MCP, plus completion, hover, references and symbols. [Odoo intelligence](../workflows/odoo-intelligence.md) explains the client and Cursor extension-host checks. These checks do not install application modules or alter a database.

## Related documents

- [Pipelines](../infrastructure/pipelines.md)
- [Python](python.md)
- [Taskfiles](taskfiles.md)
