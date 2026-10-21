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

```powershell
task setup
```

`task setup` creates `src/core/.venv`, fetches the Odoo source, installs Serena and the Odoo Language Server for the coding clients, authenticates Doppler (paste a token or browser login, selecting project `medilab`, config `dev`) and starts the containers.

Open http://localhost:8069. The `medilab` database is created by the first `task upgrade`; the database manager is turned off (`list_db = False`), so the login page shows no database administration link. Modules are installed with `task upgrade MODULES=<module>`, for example `task upgrade MODULES=sol_laboratory`.

`task upgrade MODULES=sol_laboratory,sol_demo` adds demo data and a `demo.<role>` user per role; their password is `demo`, or `MEDILAB_DEMO_PASSWORD` at install when it is set.

## Services

| Service     | URL                   | Notes                                                              |
| ----------- | --------------------- | ------------------------------------------------------------------ |
| Odoo        | http://localhost:8069 | port `MEDILAB_ODOO_PORT`                                           |
| Postgres    | `localhost:15432`     | port `MEDILAB_DB_PORT`; see [Environment](#environment)            |
| CloudBeaver | http://localhost:8978 | port `MEDILAB_CLOUDBEAVER_PORT`; `medilab` / `admin` unless overridden |

### A second stack from a worktree

Each checkout runs its own compose project, named after its folder: the main checkout's is `medilab`, a worktree in `medilab-api` gets `medilab-api`. Containers, network and volumes are named after the project, such as `medilab-api_postgres_1`, so starting or stopping a worktree's stack, with `task` or with `docker compose` or `podman-compose` directly, never touches another checkout's.

- `task dev:setup` writes the project into `tools/infrastructure/.env`, which compose reads wherever it is run from, and keeps the other lines of the file. The file is not committed.
- A worktree that runs its own stack next to the main one adds its ports, and an image tag of its own so its build does not replace the main checkout's `medilab-odoo:local`, to that file:

```sh
MEDILAB_ODOO_PORT=8169
MEDILAB_DB_PORT=25432
MEDILAB_CLOUDBEAVER_PORT=18978
MEDILAB_ODOO_IMAGE=medilab-odoo:medilab-api
```

- With `MEDILAB_ODOO_IMAGE` set, `task up` does not build, so build the worktree's image once, and after a change of dependencies: `docker compose -f tools/infrastructure/docker-compose.yml build odoo`.
- The `postgres` MCP server connects to `localhost:15432`; for a worktree's database, set `DATABASE_URI` to its port, as [Odoo intelligence](docs/workflows/odoo-intelligence.md#database-access) says.
- Commands that reach a container go through the project, never a container name: `docker compose -f tools/infrastructure/docker-compose.yml exec -T postgres psql -U root -d medilab`.

## Commands

| Command                    | Purpose                                                                                                  |
| -------------------------- | -------------------------------------------------------------------------------------------------------- |
| `task`                     | List all tasks                                                                                           |
| `task setup`               | Run `doppler`, `dev:setup`, `ai:setup` and `upgrade`                                                     |
| `task up`                  | Start Odoo, Postgres and CloudBeaver                                                                     |
| `task doppler`             | Log the Doppler CLI in and select project `medilab`, config `dev`                                        |
| `task stop`                | Stop the containers and keep the volumes                                                                 |
| `task restart`             | Restart Odoo after changing Python, XML or config                                                        |
| `task logs`                | Follow the Odoo log                                                                                      |
| `task upgrade`             | Upgrade all installed modules                                                                            |
| `task upgrade MODULES=a,b` | Install and upgrade the listed modules                                                                   |
| `task reset`               | Delete the database and volumes, then start again                                                        |
| `task dev:setup`           | Sync `src/core/.venv` from `uv.lock`, fetch the Odoo source and link the modules into it for type checks, and set this checkout's compose project |
| `task ai:setup`            | Install Serena, OdooLS and its Odoo source in this worktree for the coding clients                       |
| `task ai:odoo-ls`          | Install the pinned OdooLS release, typeshed and Odoo source that the `odoo` MCP server uses              |
| `task ai:test`             | Run the AI tooling tests and lint checks                                                                 |
| `task ai:verify`           | Check Odoo model and field navigation through the `odoo` MCP server                                      |
| `task ai:cursor-setup`     | Install the official Odoo extension into an isolated Cursor profile                                      |
| `task dev:lock`            | Re-resolve `uv.lock` after editing dependencies in `pyproject.toml`                                      |
| `task lint`                | Run ruff and pylint-odoo on `src/core/modules`                                                           |
| `task format`              | Format `src/core/modules` with ruff                                                                      |
| `task typecheck`           | Type check the modules with pyright                                                                      |

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
    infrastructure/             # docker-compose.yml and CloudBeaver config
    taskfiles/                  # app.taskfile.yml, dev.taskfile.yml
    typecheck/                  # pyright runner and the links into the Odoo source
  .github/                      # CI workflow and odoo-lint action
```
