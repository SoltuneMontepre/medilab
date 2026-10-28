# Testing

How tests are written, where they live and how they run.

## Layers

| Layer         | Tool                                             | Location                                 | Command                                                |
| ------------- | ------------------------------------------------ | ---------------------------------------- | ------------------------------------------------------ |
| Odoo modules  | Odoo test runner (`TransactionCase`, `HttpCase`) | `src/core/modules/<module>/tests/`       | `task test:core`                                       |
| Browser       | Cypress                                          | `src/tests/cypress/e2e/`                 | `task test:e2e`                                        |
| Applications  | `bun test`, Jest and `cargo test`                | next to the code, in each application    | `task test:apps`                                       |
| Type checking | `unittest` and pyright                           | `tools/typecheck/`                       | `task test:typecheck`                                  |
| Tool scripts  | `unittest`                                       | next to the script in `tools/scripts/`   | the task of the script                                 |
| AI tooling    | pytest, MCP and official OdooLS                  | `tools/odoo-intelligence/tests/`         | `task ai:test`                                         |
| Taskfiles     | `unittest` and Task                              | `tools/scripts/test_taskfile_modules.py` | `task test:taskfiles`                                  |
| CloudBeaver   | unittest and pinned containers                   | `tools/cloudbeaver/`                     | `python3 -m unittest discover -s tools/cloudbeaver -v` |

`task test` runs the module and application tests. Browser tests run against the running app, so start it first with `task up`.

## Odoo module tests

- Odoo only finds tests in the module's own `tests/` package. Its `__init__.py` imports every test file.
- One test class per file, named after the file: `test_parameter_constraints.py` holds `TestParameterConstraints`.
- Tag each class `@tagged("post_install", "-at_install")`.
- Use `TransactionCase` for models and `HttpCase` for ordinary route contracts. Tests that prove HTTP commit/rollback behavior require a separate normal HTTP process and independent database transactions; `HttpCase` shares a test cursor and cannot establish those commits.
- Routes of the laboratory files API are tested through `LaboratoryApiCase` (`sol_laboratory/tests/laboratory_api_case.py`), which checks every answer against the API's OpenAPI document: a documented status, its required headers, a body matching its schema and the status of a refusal's code. A route whose answer the document does not give fails its tests. Tests that call the laboratory files bucket use `LaboratoryBucketCase` (`sol_laboratory/tests/laboratory_bucket_case.py`) against the Garage server of Docker Compose, which `task test:core` sets up first; it calls presigned addresses as computers do. The reconciliation tests use a bucket of their own, `laboratory-files-reconcile`, which they empty before and after each test. Races of two real transactions use `laboratory_files_concurrency_case.py`; retries inside a request are tested by making a step fail on concurrency on its first try.
- `test_laboratory_editing_http.py` reuses the committed editing/concurrency fixtures and starts a separate normal Odoo process, without `--test-enable` or shared test cursors. Fresh database transactions check state after each native callback response, including real PostgreSQL serialization failures, request retries, bucket failures and rolled-back object cleanup. A local signed HTTP source stands in for Document Server; these tests do **not** satisfy pinned Document Server or staging acceptance. Its Garage bucket `laboratory-files-callback-http` is separate from other shards and has a database ownership marker; cleanup deletes only this test's bytes/marker. The existing model race suite shares `laboratory_editing_concurrency_case.py`.
- The editor HTML contract uses `test_laboratory_editor_page.py` (`HttpCase`) and pure origin-validation tests. `test_laboratory_editor_http.py` reuses the normal HTTP/concurrency harness with its separate `laboratory-files-editor-http` bucket, real CSRF-protected login/logout, concurrent opens and independent committed-state assertions. It also checks botocore DEBUG signing diagnostics for leaks. These are not real Document Server tests. `laboratory_editor.cy.js` exercises the page with a DocsAPI test double in English/Vietnamese at narrow/wide sizes, plus XSS, login, timeout and refresh/error handling; it is visibly skipped when the server lacks valid editing configuration/health. Run it explicitly against a controlled healthy fixture. Cypress strips CSP by default; a CSP claim needs a run retaining the relevant directives, and a direct browser check for directives Cypress necessarily strips. Real two-person docx/xlsx/pptx editing, long sessions, outages and callback persistence remain separate pinned-server/staging gates.
- `task test:core` uses the selected, ownership-checked Compose project. It refuses a preexisting test database, shard database or Odoo test directory, records a local test-run marker, installs the modules in that throwaway database, copies it once per shard and runs the shards at once, each with the `--test-tags /<module>:<class>` of its classes. `tools/scripts/test_shards.py` splits the classes so each shard has about the same number of test methods. The output of each shard starts with `[shard <n>]`. The task removes only its marked test databases and directory afterwards; an interrupted run with a marker requires review before another run. `MEDILAB_TEST_DB` names the test database, `medilab_test` by default; give each run its own name when two run against the same Postgres. A worktree's compose project has a Postgres of its own, so `task test:core` there leaves the main checkout's alone once the worktree has its own ports ([A second stack from a worktree](../../README.md#a-second-stack-from-a-worktree)). `task test:core MODULES=a,b` limits it to those modules; by default it runs every module in `src/core/modules.txt`.
- `task test:core RUNNER=2 RUNNERS=3` splits the classes into four shards per machine and runs the second machine's four; `ci-core` runs three machines this way. `EXCLUDE=<module>` leaves a module out, `TEST_MODULES=a,b` runs the tests of only those modules while all are installed, and `INSTALL_COVERAGE=false` installs without coverage, which is about 60% faster. With `COVERAGE_DIR=<folder>` the task saves its raw coverage data there instead of writing the report, and `task test:core:coverage COVERAGE_DIR=<folder>` combines the data of all machines into the report.
- Tests in different classes run in different processes and databases, so a test never depends on another class having run.
- `task test:uninstall` installs Laboratory, E-commerce and Inventory in a guarded throwaway database, uninstalls E-commerce and Inventory, and checks that the Laboratory data is intact. It refuses a selected fresh demo because its standalone test uses the application's filestore.
- `task test:core` also combines the coverage of the install and of every shard into the report `src/core/modules/coverage.xml`, which is not committed. Task installs its pinned Linux Python 3.12 coverage package into ignored `.local/core-test-coverage` on the host and mounts it read-only in test containers, so a container with restricted DNS can still run coverage without changing the saved application image.

## CloudBeaver tests

Run `python3 -m unittest discover -s tools/cloudbeaver -v` with Docker or Podman and the pinned CloudBeaver/PostgreSQL images. `CONTAINER_ENGINE` accepts `docker` (default) or `podman`; executable paths and additional arguments are rejected. It uses synthetic accounts and disposable volumes. Without `MEDILAB_KUBE_TEST_CONFIG`, the real Kubernetes cases report skips, not passes.

For Pod/PVC/Service/IngressRoute lifecycle tests, create a disposable kind cluster named `medilab-286-review`, using the pinned node image and image-loading recipe in [ci-infra](../../.github/workflows/ci.infra.yml). Select its separate kubeconfig explicitly:

```bash
MEDILAB_KUBE_TEST_CONFIG=/path/to/disposable-kind-config python3 -m unittest discover -s tools/cloudbeaver -p test_kubernetes.py -v
```

The harness requires context `kind-medilab-286-review`, a loopback API server and the exact single disposable node name. It creates its own namespaces, synthetic Secrets, PVCs, Traefik CRDs and test routing. Never supply a production kubeconfig. For rootless Podman, create and load the cluster inside `systemd-run --user --scope -p Delegate=yes` as described in [kind's rootless documentation](https://kind.sigs.k8s.io/docs/user/rootless/). A control plane accepting manifests does not prove Pod lifecycle tests executed.

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

- A test file is named `<feature>.cy.js` under `src/tests/cypress/e2e/`. Business-flow specs belong to `flows/<flow>/`; feature specs without an owning flow belong to `features/<module>/<feature>/`. The [browser test layout](../../src/tests/cypress/e2e/README.md) maps issue scopes to directories and spec basenames.
- Every feature has a browser test of its main path, written with the feature: it signs in as the demo user of the role that does the work, such as `demo.tester`, and walks the main path on the demo data.
- The support entry point `cypress/support/e2e.js` registers the shared commands below and keeps Odoo from subscribing to web push, which the test browser cannot do. Tests use them instead of copying sign-in, navigation or action steps. `call(<model>, <method>, <args>, <kwargs>)` from `cypress/support/odoo.js` calls a model method in the signed-in session and fails on an RPC error. Existing tests may still import `signIn(<login>)` from that file; it uses the same session handling as `cy.signInAs()`.
- Tests use the app address `MEDILAB_URL`, default `http://localhost:8069`.
- Tests do not depend on data a previous test created.
- The task unsets `ELECTRON_RUN_AS_NODE`, which editors such as VS Code set and which stops Cypress from starting.
- `task test:e2e:app` installs every module with the demo data into the app's database and starts Odoo, then waits until it answers. `ci-core` runs it before `task test:e2e`, so tests can sign in as the demo users. Locally it changes the database of `task up`; it refuses a selected fresh demo to avoid reinstalling into its completed application database.

### Running browser tests

Run commands from the repository root in PowerShell, Bash or your usual terminal. Install [Bun](https://bun.sh/docs/installation) and Node.js 22.x, 24.x or >=26 for Cypress 16, start Docker or Podman and prepare a local demo with the [README quick start](../../README.md#quick-start). Browser tests use `demo.<role>` accounts and change demo records.

1. Run `task test:e2e:help` to see the selected Odoo URL and the available commands.
2. Run `task up` to start an existing demo, then open that URL in your browser and check that the login page loads. Use `task logs` if startup fails. A completed fresh demo already has its starting records; use it directly. For a disposable test environment without demo data, `task test:e2e:app` installs the modules and demo data into its application database, as CI does.
3. Choose one of the following modes. Each checks Odoo's health, installs the locked test dependencies and ensures the matching Cypress binary is installed. Each clears `ELECTRON_RUN_AS_NODE` for Cypress.

| Mode | Command | What to do next |
| --- | --- | --- |
| Cypress App | `task test:e2e:open` | Choose **E2E Testing**, a browser, **Start E2E Testing**, then a spec such as `login.cy.js`. Inspect commands in the left panel and the page in the right panel. Saving a spec reruns it. Close the app to finish. |
| All specs in the terminal | `task test:e2e` | Read the per-spec results and final passed/failed counts. A failing run returns a nonzero exit code. |
| Some tests in the terminal | `task test:e2e GREP=TC-WF01-A5` or `task test:e2e SPEC=cypress/e2e/login.cy.js` | `GREP` runs the tests whose title contains the text, such as one test case ID or `TC-WF01` for a flow, and loads only the specs that have one. `SPEC` takes Cypress spec paths or globs. Run the tests you change this way and leave the whole suite to the `e2e` job of `ci-core`. |

Both modes inherit the local environment files loaded by Task. Set `MEDILAB_DEMO_PASSWORD` to the password used when the demo was created if it differs from `demo`.

#### Preparing the application

`task test:e2e:app` prepares the selected local application for browser tests, as CI does:

1. Verify the selected Compose project. Module installation is refused on a selected fresh demo; start that completed demo with `task up` instead.
2. Start Postgres and Garage and configure the laboratory files bucket and the additional buckets used by access and reconciliation tests.
3. Run Odoo with `-i` for every application module in `src/core/modules.txt`, including `sol_demo`, then stop the installation process. The target is the application's configured database, `medilab` by default.
4. Start the Odoo service and check `/web/health`, retrying while the server starts.
5. Print the ready URL and the next commands: `task test:e2e:open` or `task test:e2e`.

The installation step installs missing modules and seeds demo records when `sol_demo` is first installed. An existing demo keeps the changes made by earlier tests. To get clean demo starting records, create another isolated demo with the [README quick start](../../README.md#quick-start). After changing installed Odoo models or views, run `task upgrade`, or limit the upgrade with `task upgrade MODULES=sol_laboratory`.

For daily work on an existing demo, run `task up` followed by the chosen Cypress mode. Use `task test:e2e:app` when preparing a disposable application for the E2E suite.

#### Selecting the Odoo URL

The address defaults to `http://localhost:8069`. A worktree or selected demo can use another port; read `MEDILAB_ODOO_PORT` in `tools/infrastructure/.env` and pass the full matching address:

```powershell
task test:e2e:open MEDILAB_URL=http://localhost:8169
task test:e2e MEDILAB_URL=http://localhost:8169
```

Save `MEDILAB_URL=http://localhost:8169` in that environment file to reuse it. The tasks print the effective URL and pass it to Cypress. Selecting a URL only chooses where tests connect; it does not start that server.

To run a single spec directly after setup, use the same URL and clear the editor's Electron setting in PowerShell:

```powershell
Push-Location src/tests
$env:MEDILAB_URL = "http://localhost:8169"
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
bunx cypress run --spec "cypress/e2e/login.cy.js"
Pop-Location
```

#### Troubleshooting

| Message | What to do |
| --- | --- |
| `Bun is not installed` | Install Bun, reopen the terminal and retry. |
| `Cypress executable not found` / `No version of Cypress is installed` | Retry `task test:e2e:open` or `task test:e2e`; both run `cypress install` even when `bun install` reports no dependency changes. If a direct CLI invocation needs repair, run `bunx cypress install` from `src/tests`. Check `CYPRESS_INSTALL_BINARY` if installation was disabled. |
| `Odoo is not reachable` / `Cypress could not verify that this server is running` | Check the printed URL. Run `task up` in the checkout that owns that demo, open the URL yourself, and inspect `task logs`. Pass `MEDILAB_URL` when the running demo uses another port. |
| `curl: (23) client returned ERROR on write` after `Starting Odoo` | This is a response-output error in the readiness probe. Open the printed Odoo URL to check the server. The Task readiness command discards the response through its portable shell redirection. |
| Demo login fails | Confirm demo data was installed and `MEDILAB_DEMO_PASSWORD` matches the password set at installation. |

The Cypress package and its downloaded application binary are installed separately; an unchanged dependency lock does not restore a removed binary cache. See the official [installation options](https://docs.cypress.io/app/references/advanced-installation) and [CLI reference](https://docs.cypress.io/app/references/command-line).

`src/tests/bun.lock` locks the Cypress version. Close Cypress App and reopen it with `task test:e2e:open` after upgrading the dependency. Cypress 16 uses `cy.env()` for secret values; its configuration follows the official [migration guide](https://docs.cypress.io/app/references/migration-guide).

### AI authoring and live debugging

Use [Cypress Tap and AI Skills](../workflows/cypress-tap.md) when an agent writes, reviews or debugs a spec. `task test:e2e:tap:open` opens this worktree with Chrome; `task test:e2e:tap TAP_ARGS="<command>"` binds the installed Tap CLI to its E2E session. A Tap dispatch is asynchronous; inspect a fresh verdict and actual test counts. The existing headless task remains the CI suite.

### Shared browser commands

| Command | Use |
| --- | --- |
| `cy.signInAs(role)` | Sign in as `demo.<role>`, for example `tester`, `head_of_department` or `customer`. Read the password from `MEDILAB_DEMO_PASSWORD`, default `demo`. First unregister Odoo's service worker: its update check after the previous backend page would get a new session cookie, which the login form's CSRF token does not match. Cache and validate the session within this spec file, then open the backend or portal as appropriate. |
| `cy.openRecord(record)` | Open the backend form of a record given by a full demo external ID such as `sol_demo.demo_test_result_retest`, or as `{ model, id }`, and yield `{ model, id }`. The current user's permissions apply. |
| `cy.readRecord(record, fields)` | Read the named fields of that record in the current session and yield its values. `fields` must be a nonempty array. |
| `cy.signRecord(action)` | Click the visible form button named `action`, default `action_sign`. |
| `cy.rejectRecord(reason, options)` | Open the rejection wizard, fill its reason, confirm and wait for it to close. `options.button` selects the opener, default the form's visible danger button; set it when there is more than one. `options.reasonField` defaults to `[name="reason"] textarea` and `options.action` to `action_reject`. |
| `cy.sendRecord(action)` | Click the visible form button named `action`, default `action_send`; pass `action_send_quotation`, `action_send_invoice` or another document's action when needed. |
| `cy.expectRefusal({ action, message, read, messageSelector })` | Take a snapshot with `read()`, run `action()`, require the visible refusal message, then compare another snapshot. Fail if that message was already present. |

The action commands use the interface. Each test asserts its expected resulting state afterwards. A refusal's `read` callback returns a Cypress chain with the persisted fields the action could change, including `write_date`, and any related records its rule protects. A missing message fails even when the record stays unchanged; a changed record fails even when the message appears. The default message containers are Odoo's error dialogs, notifications and alerts inside modals; pass `messageSelector` for a field validation or another container.

```js
cy.signInAs("tester");
cy.openRecord("sol_demo.demo_test_result_retest");
cy.expectRefusal({
  read: () => cy.readRecord("sol_demo.demo_test_result_retest", ["status", "write_date"]),
  action: () => cy.signRecord(),
  message: "The expected refusal from this flow.",
});
```

`cypress/support/odoo.js` also exports functions for building and checking records. The `…As` functions run in the test runner with one session per login for the whole run, so building a test's records never changes the browser's session or reloads the back office:

| Function | Use |
| --- | --- |
| `callAs(login, model, method, args, kwargs)` | Call a model method as a login, such as `demo.sales` or `portal.anphu`, and yield its result. |
| `refAs(login, xmlId)` | Resolve a full demo external ID as a login and yield `{ model, id }`. |
| `portalPostAs(login, page, path, form)` | Submit a portal form as a login, with the CSRF token of `page`. |
| `callRefused(model, method, args, kwargs)` | Call a model method that must be refused and yield the server's message, in the signed-in user's language. Use it with a check that the screen does not offer the action. |

`cypress/support/form.js` exports the steps for filling a form in the interface:

| Function | Use |
| --- | --- |
| `newRecord(path)` | Open a list such as `/odoo/lab-orders`, click **New** and wait until Odoo has filled in the defaults. |
| `pick(field, text)` | Type into a many2one field and click the suggestion that contains `text`. |
| `choose(field, label)` | Choose a selection field's value by its label. |
| `search(text, { grouped: false, field })` | Filter the list and wait for its response. The first search field is the default; `field` selects a label. Set `grouped: true` for a grouped list. |
| `save()` | Save the form and wait until it has no unsaved changes. |
| `openTab(name)` | Open the notebook page with that `name`. |

Messages on screen follow the user's language: `demo.sales` reads Vietnamese, most other demo users English. Odoo screens load their data after the page, so commands wait up to ten seconds.

`demo_roles.cy.js` checks every seeded demo account and opening a demo record. `browser_helpers.cy.js` checks the shared action and refusal commands on a controlled browser fixture, including that a successful action fails the refusal check. Business-flow tests create their starting records with their flow's `setup.js`, so a spec runs again on the same database, and cover only their flow's paths from [Business flows](../functional/business-flows.md).

## Applications

- Frontend tests are `*.test.ts` and `*.test.tsx` files next to the code they test, run by `bun test`.
- React Native does not run under `bun test`, so Medilab Mobile's tests run with Jest and the `jest-expo` preset through `bun run test`, and render screens with React Native Testing Library. Every file under its `src/app/` is a route, so a screen and its test live in `src/features/<area>/` and the route file only exports the screen.
- Rust tests run with `cargo test` when `cargo` is installed; `task test:apps` skips them with a message otherwise.

## AI tooling

`task ai:test` runs the tooling suite and lint checks; `ci-tools` runs it on pull requests that change the AI tooling. Live OdooLS tests run when `task ai:setup` has installed the binary and source; otherwise they report skips, as they do in CI. `task ai:verify` checks the Python and XML model and field definitions in `odoo_intelligence/navigation_cases.json` through MCP, plus completion, hover, references and symbols. [Odoo intelligence](../workflows/odoo-intelligence.md) explains the client and Cursor extension-host checks. These checks do not install application modules or alter a database.

The independent callback HTTP worker uses the parent coverage settings and a parallel data file. Its server process must terminate normally so the callback paths reach the combined report. `task test:onlyoffice:coverage` runs the runtime and fixture security contracts and writes Python XML and signing-hook LCOV under `.local/onlyoffice-coverage`. CI publishes those reports alongside Odoo coverage; Sonar imports both. The coverage checkout fetches full history so the real environment-generator regression can read both its verified pinned policy revision and the current commit. Runtime-only changes must keep the scan and runtime coverage jobs enabled.

## Related documents

- [Pipelines](../infrastructure/pipelines.md)
- [Python](python.md)
- [Taskfiles](taskfiles.md)
