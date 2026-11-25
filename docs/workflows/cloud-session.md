# Working in a cloud session

A Claude Code cloud session is a fresh Linux container with this repository cloned on a `claude/...` branch. The container is deleted when the session goes idle: only the cloud environment, pushed commits and what lives outside the container carry over to the next session.

## What carries over

The first session of an environment runs its setup script. When the script finishes within about five minutes, Claude Code keeps a snapshot of the container's files and starts later sessions from it, without running the script again. It runs the script again when the script or the allowed hosts change, and about every seven days.

| Carries over                                                          | Gone with the container                       |
| --------------------------------------------------------------------- | --------------------------------------------- |
| The environment's setup script, environment variables, network access | Running processes, such as Docker and Odoo    |
| What the setup script installed and pulled, in the snapshot           | Tools and images a session installs itself    |
| Commits pushed to GitHub                                              | The local database and what a session changed |
| Issues, pull requests, Claude Docs and artifacts                      |                                               |

## Set up the environment

Do this once, in the cloud environment `medilab`: the environment menu in the session's title bar, then Edit. Select it in the project's settings so new sessions use it.

1. On your own machine, run `task ai:env`. It logs Doppler in if needed and writes `.local/cloud.env` from the template `tools/cloud/cloud.env.example`, filling each variable from Doppler `medilab` `dev`.
2. Paste the contents of `.local/cloud.env` under Environment variables, then delete the file. Never paste it into a chat or commit it.
3. Paste this under Setup script. It installs the Doppler CLI and `task`, sends Docker Hub pulls through Google's mirror, pulls the images of the local stack and the [seed database](#the-seed-database), runs `task ai:setup` and pre-installs the `postgres` MCP server. A step that fails writes what to fix to `/var/log/medilab-setup.log` and the others still run. The script always exits successfully, since a failing script stops the session from starting; `task cloud:start` prints the log and pulls what is missing.

   ```bash
   #!/bin/bash
   # Prepares a MediLab cloud session. The environment cache keeps what it writes; the SessionStart hook starts Odoo.
   set -uo pipefail

   log=/var/log/medilab-setup.log
   : > "$log"
   warn() { printf 'setup: %s\n' "$*" | tee -a "$log" >&2; }
   export PATH="$HOME/.local/bin:$PATH"

   # Doppler CLI from its signed apt repository
   install_doppler() {
     local key
     key=$(mktemp) &&
       curl -fsSL --retry 3 -o "$key" 'https://packages.doppler.com/public/cli/gpg.DE2A7741A397C129.key' &&
       gpg --dearmor --yes -o /usr/share/keyrings/doppler-archive-keyring.gpg "$key" &&
       echo "deb [signed-by=/usr/share/keyrings/doppler-archive-keyring.gpg] https://packages.doppler.com/public/cli/deb/debian any-version main" \
         > /etc/apt/sources.list.d/doppler-cli.list &&
       apt-get update -o Dir::Etc::sourcelist=sources.list.d/doppler-cli.list -o Dir::Etc::sourceparts=- -qq &&
       apt-get install -y -qq doppler
   }
   install_doppler || warn "Doppler CLI not installed. Allow packages.doppler.com under Network access."

   # Task runner for the repository's taskfiles
   uv tool install go-task-bin || warn "task not installed."

   # Docker Hub through Google's mirror, which has no anonymous pull limit
   start_docker() {
     docker info > /dev/null 2>&1 && return
     mkdir -p /etc/docker &&
       printf '{"registry-mirrors":["https://mirror.gcr.io"]}\n' > /etc/docker/daemon.json || return 1
     nohup dockerd > /var/log/dockerd.log 2>&1 &
     for _ in $(seq 1 30); do docker info > /dev/null 2>&1 && return; sleep 1; done
     return 1
   }
   start_docker || warn "Docker did not start. See /var/log/dockerd.log."

   repo=medilab
   if [ -d "$repo" ]; then
     cd "$repo"
     # Images of the local stack and the seeded demo database, kept by the environment cache
     MEDILAB_ODOO_IMAGE=ghcr.io/soltunemontepre/medilab:latest \
       docker compose -f tools/infrastructure/docker-compose.yml pull -q ||
       warn "Could not pull the Compose images. Allow pkg-containers.githubusercontent.com under Network access."
     docker pull -q ghcr.io/soltunemontepre/medilab-seed:latest > /dev/null || warn "Could not pull the seeded database."
     if command -v task > /dev/null; then
       task ai:setup || warn "task ai:setup failed."
     fi
     uvx --python 3.13 --overrides tools/odoo-intelligence/postgres-overrides.txt \
       --with "mcp<2" postgres-mcp==0.3.0 --help > /dev/null || warn "postgres MCP server not installed."
   fi

   # Stop Docker so the cache holds a clean daemon state; the session start hook starts it again.
   pkill dockerd && while pgrep dockerd > /dev/null; do sleep 1; done
   exit 0
   ```

4. Under Network access, keep the package registries and MCP servers allowed and add these hosts to Allowed domains, one per line. The Doppler hosts serve the CLI and the secrets, and `pkg-containers.githubusercontent.com` serves the layers of the `ghcr.io` images:

   ```text
   pkg-containers.githubusercontent.com
   packages.doppler.com
   api.doppler.com
   ```

`DOPPLER_TOKEN` is the read-only service token of `dev`; `doppler run` reads the other secrets through it, so the cloud environment holds no other credential. `MEDILAB_ODOO_IMAGE` makes `task up` run the image that `cd-core` publishes instead of building one. The image carries the Python packages of `main`; the modules come from the checkout. The setup script cannot read the environment variables; the Doppler CLI reads `DOPPLER_TOKEN` later, in the session. Write scripts and Dockerfiles for a session by [Cloud network](../conventions/cloud_network.md).

## The seed database

Installing every module with the demo data takes about ten minutes, longer than the setup script may take to be cached. `cd-seed` does it every night instead: it runs `task cloud:seed`, which runs the fresh demo setup of `task setup:fresh` and saves the database, Odoo file store and Garage volumes as tar files, then publishes them as the image `ghcr.io/soltunemontepre/medilab-seed`. See [Pipelines](../infrastructure/pipelines.md#cd-seed).

## Start a session

When a session starts or resumes, the `hook-cloud-start` SessionStart hook runs `task cloud:start` in the background, so Odoo comes up while you work; outside a cloud session the hook does nothing. Its log is `.local/cloud-start.log`, which ends with `Odoo is ready` or the step that failed. `task cloud:start`:

1. Prints the problems the setup script reported, if any.
2. Starts Docker.
3. Restores the seed database into the stack's volumes when the database volume is missing, pulling the seed image if the snapshot does not have it.
4. Installs and upgrades this checkout's modules with `task upgrade`, unless it already did so for the same commit, then starts the stack.
5. Waits until Odoo answers at `http://localhost:8069`.

While Odoo starts:

1. Check the branch with `git status` and `git log --oneline -3`. If its pull request is already merged, restart the branch from `origin/main`.
2. Read `AGENTS.md`, then `docs/readme.md`, and activate the project in Serena.
3. If the setup script did not run `task ai:setup`, install `task` with `uv tool install go-task-bin`, then run `task ai:setup` and `task ai:verify`. The `odoo` MCP server works right after, in the same session.
4. Run `git fetch --unshallow origin main` before `git log -S` or `git blame`: the clone is shallow.

## Run the app

Odoo runs at `http://localhost:8069`, which the built-in Chromium opens, with the demo users of `sol_demo` and the password `demo`. After changing a module, run `task upgrade MODULES=<module>`. To start it again, run `task cloud:start`.

The database listens on `localhost:15432` with user and password `root`. The `postgres` MCP server connects when the session starts, usually before the database is up; query the database with `PGPASSWORD=root psql -h localhost -p 15432 -U root -d medilab`.

## Limits

| Limit                              | What to do                                                                      |
| ---------------------------------- | ------------------------------------------------------------------------------- |
| The container is deleted when idle | Commit and push before leaving                                                  |
| A tool a session installs is gone  | Add it to the setup script                                                      |
| A setup script over five minutes   | Move the slow step to `cd-seed` or `task cloud:start`; it is not cached         |
| A host is refused by the proxy     | Allow it under Network access, or attach your own computer with Remote Control  |
| Production cannot be reached       | Reproduce locally, or give the exact URLs or queries to someone with access     |
| No `gh` CLI                        | Use the GitHub MCP tools for issues, pull requests, comments and CI             |
| The disk allowance runs out        | Delete build artifacts, Docker images and caches; deletes work when writes fail |
| One branch per session             | Work and push only on the session's `claude/...` branch                         |

## Related documents

- [Cloud network](../conventions/cloud_network.md)
- [Secrets](../infrastructure/secrets.md)
- [Pipelines](../infrastructure/pipelines.md#cd-seed)
- [Odoo intelligence](odoo-intelligence.md)
- [Taskfile conventions](../conventions/taskfiles.md)
- [Claude Code cloud environments](https://code.claude.com/docs/en/cloud-environments)
