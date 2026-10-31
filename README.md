# Medilab

![MediLab banner](docs/assets/banner.svg)

[![SonarQube Cloud](https://sonarcloud.io/images/project_badges/sonarcloud-light.svg)](https://sonarcloud.io/summary/new_code?id=SoltuneMontepre_medilab2)

Laboratory Information Management System (LIMS) for testing laboratories, built on Odoo 20.0. Modules:

- [E-commerce](docs/functional/ecommerce_module/overview.md)
- [Laboratory](docs/functional/laboratory_module/overview.md)
- [Inventory](docs/functional/inventory_module/overview.md)
- Medilab Theme (`sol_theme`), optional: the MediLab look

Documentation index: [docs/readme.md](docs/readme.md).

## Prerequisites

Run commands from this checkout in a Linux terminal or native Windows PowerShell. Task uses its embedded shell; Git Bash and commands inside WSL are not required. Docker Desktop still needs a working Linux-container backend.

| Tool | Purpose |
| --- | --- |
| Python 3.12+ and Git on `PATH` | Portable setup and worktree ownership |
| [Task](https://taskfile.dev/docs/installation) | Root entrypoint; the Arch package is `go-task` |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | Existing locked Python environments |
| Local Docker-compatible CLI and Compose | Docker Engine server >=28 or supported Podman exposing `docker`, a local Linux amd64 engine and a provider supporting `!override` (Docker Compose 2.24.4+) |
| [Node.js](https://nodejs.org/en/download) 20.19+ (20.x) or >=22.12, including npm/npx | AI tooling and application tooling |
| [Bun](https://bun.sh/docs/installation) stable >=1.4.0 | Locked frontend and Tauri CLI dependencies; the committed Sync lockfile uses format 2 |
| Rust/Cargo and [Tauri native dependencies](https://v2.tauri.app/start/prerequisites/) | Native Sync checks and compilation |
| [Doppler CLI](https://docs.doppler.com/docs/install-cli) | Authentication for an existing ordinary environment; a fresh local demo does not use it |

Allocate at least four CPUs and 8 GiB to the container engine: the pinned ONLYOFFICE service reserves up to 6 GiB, with additional capacity for Odoo and storage. Start the daemon before setup. A shell alias for `docker` is insufficient; Task must find the executable and Compose provider on `PATH`. Remote engines are refused. Docker Engine server 28+ is required for isolated editor networking; a newer CLI connected to an older server is insufficient.

On Arch/CachyOS install the native Tauri development libraries described in the linked Arch instructions, including WebKitGTK 4.1, GTK/appindicator, OpenSSL and the compiler/pkg-config toolchain. On Windows install the MSVC Rust target, Microsoft C++ Build Tools with the desktop C++ workload/Windows SDK, and WebView2. These are native OS prerequisites; setup does not elevate, install another runtime manager, change global trust or silently skip missing compilers. Restart the terminal after installing tools. If Windows resolves `python` to its Store alias, disable that alias and install native Python.

The committed Sync lockfile requires stable Bun >=1.4.0, which introduced [lockfile format 2](https://bun.com/blog/bun-v1.4#bun-lock-is-now-lockfileversion-2). Setup refuses incompatible Bun before changing the application; keep the lockfile unchanged. The locked Vite 7 frontend requires Node 20.19+ (20.x) or >=22.12. Cypress 16 has its own supported Node versions (22.x, 24.x or >=26); use those when running the browser suite as well.

## Quick start

```powershell
task setup
```

Setup checks host prerequisites before authentication or application changes. In an empty worktree it selects a deterministic, isolated fresh project with available ports and reuses the guarded bootstrap: Vietnamese accounting, all MediLab modules, demo users and private report assets. It prepares the existing development/AI tooling, ONLYOFFICE integration and frozen native Sync dependencies, including an actual locked Cargo check after building the frontend. The fresh branch uses local development credentials without Doppler and prevents nested tasks from reloading private caller dotenv credentials.

For an existing ordinary local environment, setup first recovers owned ONLYOFFICE registration and checks for unmanaged editor configuration, then preserves the selected database/storage and the Doppler → development tooling → AI tooling → installed-module upgrade flow. `MODULES=sol_laboratory` limits that upgrade; a fresh bootstrap always installs its complete demo module set. An existing base-only database cannot pass the required Laboratory/Sync API verification, and setup does not install `sol_demo` into it automatically.

Setup verifies actual API readiness/authentication and a disposable ONLYOFFICE conversion, then restores the test objects it owns. It does not open the desktop app. Use:

```powershell
task sync:dev
```

Standalone `sync:setup`, `sync:verify` and `sync:dev` require a saved selection for this worktree and verify its running Odoo container and published port before API access. They do not accept another checkout's server merely because localhost:8069 answers. Offline `sync:build`, `sync:test`, `sync:lint` and `sync:check` do not require a running backend once frozen frontend dependencies are installed.

The native app retains its installed settings, queue and credentials. Its saved Odoo URL takes precedence over the development build default; inspect the app's Settings when switching environments. Setup saves only worktree development endpoint metadata. Ports 1420/1421 must be available before starting native development.

Rerunning setup preserves the owned database, volume identities, certificates and JWT. Interrupted or ambiguous bootstrap ownership is refused with recovery guidance; missing completed addon data or private material is not regenerated silently. To choose a project explicitly, run `task setup:fresh:select PROJECT=medilab-bootstrap-<name>` before `task setup`. The `setup:fresh`, switching and owner-confirmed recovery commands are backend lifecycle operations. See [local setup](docs/workflows/setting-up.md#local-demo-setup).

Open the Odoo address printed by setup (8069 when free), also saved as `MEDILAB_ODOO_PORT` in `tools/infrastructure/.env`. Demo users sign in as `demo.<role>` with password `demo`. Setup also prints ONLYOFFICE's browser-facing loopback HTTP address; `task onlyoffice:status` can show it again as `public_url`. Its canonical Document Server and internal gateway use verified TLS without adding a CA to the host trust store. The setup/conversion checks do not establish full browser editing, callback-save or installed-release acceptance.

## Services

These are the default ports for an ordinary local stack. A selected fresh demo uses the ports saved in `tools/infrastructure/.env`.

| Service     | URL                   | Notes                                                                                                                           |
| ----------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Odoo        | http://localhost:8069 | port `MEDILAB_ODOO_PORT`                                                                                                        |
| ONLYOFFICE  | Printed by setup      | managed loopback address; `task onlyoffice:status` reports `public_url`                                                         |
| Postgres    | `localhost:15432`     | port `MEDILAB_DB_PORT`; see [worktree port configuration](#a-second-stack-from-a-worktree)                                                                         |
| CloudBeaver | http://localhost:8978 | port `MEDILAB_CLOUDBEAVER_PORT`; `medilab` / `admin` unless overridden                                                          |
| Garage      | http://localhost:3900 | the laboratory files bucket, port `MEDILAB_GARAGE_PORT`; its admin API is on `127.0.0.1:3903`, port `MEDILAB_GARAGE_ADMIN_PORT` |

### A second stack from a worktree

Each checkout runs its own compose project, named after its folder: the main checkout's is `medilab`, a worktree in `medilab-api` gets `medilab-api`. Containers, network and volumes are named after the project, such as `medilab-api_postgres_1`, so starting or stopping a worktree's stack, with `task` or with `docker compose` or `podman-compose` directly, never touches another checkout's.

- `task dev:setup` writes the project into `tools/infrastructure/.env`, which compose reads wherever it is run from, and keeps the other lines of the file. The file is not committed.
- A worktree that runs its own stack next to the main one adds its ports, and an image tag of its own so its build does not replace the main checkout's `medilab-odoo:local`, to that file:

```sh
MEDILAB_ODOO_PORT=8169
MEDILAB_DB_PORT=25432
MEDILAB_CLOUDBEAVER_PORT=18978
MEDILAB_GARAGE_PORT=13900
MEDILAB_GARAGE_ADMIN_PORT=13903
BUCKET_LABORATORY_PUBLIC_ADDRESS=http://localhost:13900
MEDILAB_ODOO_IMAGE=medilab-odoo:medilab-api
```

- `BUCKET_LABORATORY_PUBLIC_ADDRESS` follows `MEDILAB_GARAGE_PORT`, since it is the address the browser uploads to.
- With `MEDILAB_ODOO_IMAGE` set, `task up` does not build, so build the worktree's image once, and after a change of dependencies: `docker compose -f tools/infrastructure/docker-compose.yml build odoo`.
- The `postgres` MCP server connects to `localhost:15432`; for a worktree's database, set `DATABASE_URI` to its port, as [Odoo intelligence](docs/workflows/odoo-intelligence.md#database-access) says.
- Commands that reach a container go through the project, never a container name: `docker compose -f tools/infrastructure/docker-compose.yml exec -T postgres psql -U root -d medilab`.

## Browser tests

Run these commands from the repository root. Start Docker or Podman and use a local demo environment with the demo data installed; the tests change its records. For a new demo, follow [Quick start](#quick-start) first.

```powershell
task test:e2e:help
task up
task test:e2e:open
```

In Cypress App, choose **E2E Testing**, select a browser, click **Start E2E Testing**, then choose a file such as `login.cy.js`. Saving a test reruns it in that window. Close Cypress App when finished. To run all tests in the terminal:

```powershell
task test:e2e
```

Both modes print and check the Odoo URL, install the locked dependencies and install the matching Cypress binary if it is missing. A stopped server produces a message with the next command to run. Cypress does not start Odoo or seed its database.

`task test:e2e:app` prepares a disposable E2E environment: it checks the selected Compose project, starts Postgres and Garage, configures the test buckets, installs the modules and demo data, starts Odoo and waits for `/web/health`. It uses the selected application's database. For an existing demo, use `task up`; after changing Odoo models or views, use `task upgrade`. Then use `task test:e2e:open` or `task test:e2e` to run tests. See [application preparation](docs/conventions/testing.md#preparing-the-application) for the installation and demo-data behavior.

The Cypress version is locked in `src/tests/bun.lock`. After a dependency upgrade, close any running Cypress App window and reopen it with `task test:e2e:open` to use the installed version.

If the demo uses another port, pass its address to either mode:

```powershell
task test:e2e:open MEDILAB_URL=http://localhost:8169
task test:e2e MEDILAB_URL=http://localhost:8169
```

Use the Odoo port saved in `tools/infrastructure/.env`; save `MEDILAB_URL` there to reuse the address. The default is `http://localhost:8069`. See [the browser test guide](docs/conventions/testing.md#running-browser-tests) for setup, troubleshooting and running a single spec.

For AI authoring and live debugging, use `task test:e2e:tap:open` and the [Cypress Tap workflow](docs/workflows/cypress-tap.md). The repository includes the official author, explain, docs and Tap skills for Codex, Cursor, Antigravity and Claude Code.

## Commands

| Command                    | Purpose                                                                                                                                           |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task`                     | List all tasks                                                                                                                                    |
| `task setup`               | Diagnose and prepare Odoo, ONLYOFFICE and native Sync; verify required integration contracts                                                                                              |
| `task setup:fresh:select PROJECT=medilab-bootstrap-<name>` | Select an empty demo project and available ports for this checkout                                                        |
| `task setup:fresh`         | Initialize and seed the selected fresh demo, or start it again after successful bootstrap                                                        |
| `task up`                  | Start Odoo, Postgres, Garage and CloudBeaver                                                                                                      |
| `task doppler`             | Log the Doppler CLI in and select project `medilab`, config `dev`                                                                                 |
| `task stop`                | Stop the containers and keep the volumes                                                                                                          |
| `task restart`             | Restart Odoo after changing Python, XML or config                                                                                                 |
| `task logs`                | Follow the Odoo log                                                                                                                               |
| `task upgrade`             | Upgrade all installed modules                                                                                                                     |
| `task upgrade MODULES=a,b` | Install and upgrade the listed modules                                                                                                            |
| `task reset`               | Recreate a verified fresh demo after confirming its owner; ordinary environments are refused                                                     |
| `task clean`               | Delete a verified fresh demo, its image and its selection after confirming its owner, without recreating it                                      |
| `task dev:setup`           | Sync `src/core/.venv` from `uv.lock`, fetch the Odoo source and link the modules into it for type checks, and set this checkout's compose project |
| `task ai:setup`            | Install Serena, OdooLS and its Odoo source in this worktree for the coding clients                                                                |
| `task ai:odoo-ls`          | Install the pinned OdooLS release, typeshed and Odoo source that the `odoo` MCP server uses                                                       |
| `task ai:test`             | Run the AI tooling tests and lint checks                                                                                                          |
| `task test:taskfiles`       | Check module selection and browser-test setup without running containers or Cypress                                                               |
| `task test:e2e:help`        | Show browser-test setup, the selected Odoo URL and troubleshooting                                                                                |
| `task test:e2e:open`        | Open Cypress App to choose, watch and debug a test                                                                                                 |
| `task test:e2e:tap:open`    | Open this worktree with Chrome for live AI debugging                                                                                             |
| `task test:e2e:tap TAP_ARGS='status --json'` | Inspect this worktree's live Cypress E2E session                                                                                         |
| `task test:e2e`             | Run every browser test against the running local demo                                                                                             |
| `task test:e2e:app`         | Install demo data and start the disposable browser-test application, as CI does                                                                   |
| `task ai:verify`           | Check Odoo model and field navigation through the `odoo` MCP server                                                                               |
| `task ai:cursor-setup`     | Install the official Odoo extension into an isolated Cursor profile                                                                               |
| `task dev:lock`            | Re-resolve `uv.lock` after editing dependencies in `pyproject.toml`                                                                               |
| `task lint`                | Run ruff and pylint-odoo on `src/core/modules`                                                                                                    |
| `task format`              | Format `src/core/modules` with ruff                                                                                                               |
| `task typecheck`           | Type check the modules with pyright                                                                                                               |

Ordinary tasks load `src/core/.env.local`. Fresh setup passes sanitized child environments and an empty dotenv override. To run a tool outside Task: `uv run --project src/core --env-file src/core/.env.local <command>`.

### Component development commands

- `task onlyoffice:setup`, `onlyoffice:up`, `onlyoffice:down`, `onlyoffice:restart`, `onlyoffice:status`, `onlyoffice:logs`, `onlyoffice:verify` and `onlyoffice:config:check` manage the selected owned addon. Down retains volumes and private material; status/config checks do not initialize state.
- `task sync:doctor`, `sync:setup`, `sync:dev`, `sync:build`, `sync:test`, `sync:lint`, `sync:check`, `sync:verify` and `sync:clean` operate from the root. Build creates native release packages using the existing release targets: NSIS on Windows and DEB/RPM on Linux, with locked Cargo dependencies. Clean removes only fixed build outputs, never installed app state.
- Existing `up`, `logs`, `upgrade`, Terraform and test commands do not acquire native Sync prerequisites just because these taskfiles are included.

## Layout

```text
medilab/
  taskfile.yml                  # entrypoint
  docs/                         # documentation
  src/
    core/                       # the Odoo app
      config/odoo.conf          # mounted as /etc/odoo
      modules/                  # Odoo addons, mounted as /mnt/extra-addons
      modules.txt               # module list
      pyproject.toml            # Python dependencies and Ruff config
      uv.lock
      .env.local                # local credentials
    applications/               # other applications
      medilab-mobile/
      medilab-sync/
  tools/
    dockerfiles/                # prod.dockerfile
    infrastructure/             # docker-compose.yml, the CloudBeaver config and the Garage setup
    taskfiles/                  # app.taskfile.yml, dev.taskfile.yml
    typecheck/                  # pyright runner and the links into the Odoo source
  .github/                      # CI workflow and odoo-lint action
```
