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

| Tool                                                     | Purpose                                            |
| -------------------------------------------------------- | -------------------------------------------------- |
| Docker or Podman                                         | Runs the container stack                           |
| [Task](https://taskfile.dev/installation/)               | `task` CLI for setup and daily commands            |
| [uv](https://docs.astral.sh/uv/)                         | Python environment for linting and typecheck       |
| [Doppler CLI](https://docs.doppler.com/docs/install-cli) | Secrets                                            |
| [Node.js](https://nodejs.org/en/download)                | `npx` for the `doppler` and `context7` MCP servers |

## Quick start

For a new local demo environment:

```powershell
task setup:fresh:select PROJECT=medilab-bootstrap-local
task setup:fresh
```

Selection saves an empty Compose project and available host ports for this checkout. It leaves existing projects and their data intact, including resources from a previous `task setup`. The bootstrap creates `src/core/.venv`, fetches the Odoo source, installs Serena and the Odoo Language Server, initializes the Vietnamese accounting chart and seeds the MediLab demo data with private report assets. It uses local development credentials without Doppler.

Open the Odoo port printed by selection, also saved as `MEDILAB_ODOO_PORT` in `tools/infrastructure/.env`. The database manager is turned off (`list_db = False`), so the login page shows no database administration link. Demo users sign in as `demo.<role>` with password `demo`.

For an existing local environment, `task setup` prepares the tooling, authenticates Doppler (project `medilab`, config `dev`) and upgrades installed modules. Install other modules with `task upgrade MODULES=<module>`, for example `task upgrade MODULES=sol_laboratory`. Installing `sol_demo` through `task upgrade` is refused unless it is already installed; use the fresh bootstrap for a new demo. See [local demo setup](docs/workflows/setting-up.md#local-demo-setup) for recovery and switching projects.

## Services

These are the default ports for an ordinary local stack. A selected fresh demo uses the ports saved in `tools/infrastructure/.env`.

| Service     | URL                   | Notes                                                                                                                           |
| ----------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Odoo        | http://localhost:8069 | port `MEDILAB_ODOO_PORT`                                                                                                        |
| Postgres    | `localhost:15432`     | port `MEDILAB_DB_PORT`; see [Environment](#environment)                                                                         |
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

## Commands

| Command                    | Purpose                                                                                                                                           |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task`                     | List all tasks                                                                                                                                    |
| `task setup`               | Run `doppler`, `dev:setup`, `ai:setup` and `upgrade`                                                                                              |
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
| `task dev:setup`           | Sync `src/core/.venv` from `uv.lock`, fetch the Odoo source and link the modules into it for type checks, and set this checkout's compose project |
| `task ai:setup`            | Install Serena, OdooLS and its Odoo source in this worktree for the coding clients                                                                |
| `task ai:odoo-ls`          | Install the pinned OdooLS release, typeshed and Odoo source that the `odoo` MCP server uses                                                       |
| `task ai:test`             | Run the AI tooling tests and lint checks                                                                                                          |
| `task test:taskfiles`       | Check module selection in setup and upgrade commands without running containers                                                                    |
| `task ai:verify`           | Check Odoo model and field navigation through the `odoo` MCP server                                                                               |
| `task ai:cursor-setup`     | Install the official Odoo extension into an isolated Cursor profile                                                                               |
| `task dev:lock`            | Re-resolve `uv.lock` after editing dependencies in `pyproject.toml`                                                                               |
| `task lint`                | Run ruff and pylint-odoo on `src/core/modules`                                                                                                    |
| `task format`              | Format `src/core/modules` with ruff                                                                                                               |
| `task typecheck`           | Type check the modules with pyright                                                                                                               |

Every task loads `src/core/.env.local`. To run a tool outside Task: `uv run --project src/core --env-file src/core/.env.local <command>`.

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
