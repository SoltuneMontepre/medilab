# Working in a cloud session

A Claude Code cloud session is a fresh Linux container with this repository cloned on a `claude/...` branch. The container is deleted when the session goes idle: only the cloud environment's settings, pushed commits and what lives outside the container carry over to the next session.

## What carries over

| Carries over                                                          | Gone with the container                                      |
| --------------------------------------------------------------------- | ------------------------------------------------------------ |
| The environment's setup script, environment variables, network access | Tools a session installs, such as `task` and the Doppler CLI |
| Commits pushed to GitHub                                              | The OdooLS install and Odoo mirror of `task ai:setup`        |
| Issues, pull requests, Claude Docs and artifacts                      | The Docker daemon, its images and the local database         |

## Set up the environment

Do this once per cloud environment, in its settings: the environment menu in the session's title bar, then Edit. New sessions pick the changes up.

1. On your own machine, run `task ai:env`. It logs Doppler in if needed and writes `.local/cloud.env` from the template `tools/cloud/cloud.env.example`, filling each variable from Doppler `medilab` `dev`.
2. Paste the contents of `.local/cloud.env` under Environment variables, then delete the file. Never paste it into a chat or commit it.
3. Paste this under Setup script. It installs the Doppler CLI and `task`, sends Docker Hub pulls through Google's mirror and starts Docker. When the repository is already cloned, it also runs `task ai:setup`, pre-installs the `postgres` MCP server and starts the database, so that server connects at session start. A step that fails prints what to fix and the others still run; the script then exits with an error.

   ```bash
   #!/bin/bash
   set -uo pipefail

   failed=0
   warn() { printf 'setup: %s\n' "$*" >&2; failed=1; }
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
   install_doppler || warn "Doppler CLI not installed. Allow packages.doppler.com and api.doppler.com under Network access."

   # Task runner for the repository's taskfiles
   uv tool install go-task-bin || warn "task not installed."

   # Docker Hub through Google's mirror, which has no anonymous pull limit
   start_docker() {
     docker info > /dev/null 2>&1 && return
     mkdir -p /etc/docker &&
       printf '{"registry-mirrors":["https://mirror.gcr.io"]}\n' > /etc/docker/daemon.json || return 1
     nohup dockerd > /tmp/dockerd.log 2>&1 &
     for _ in $(seq 1 30); do docker info > /dev/null 2>&1 && return; sleep 1; done
     return 1
   }
   start_docker || warn "Docker did not start. See /tmp/dockerd.log."

   repo=/home/user/medilab
   if [ -d "$repo" ] && command -v task > /dev/null; then
     cd "$repo"
     task ai:setup || warn "task ai:setup failed."
     uvx --python 3.13 --overrides tools/odoo-intelligence/postgres-overrides.txt \
       --with "mcp<2" postgres-mcp==0.3.0 --help > /dev/null || warn "postgres MCP server not installed."
     if docker info > /dev/null 2>&1; then
       { task dev:compose-env &&
         docker compose -f tools/infrastructure/docker-compose.yml up -d --wait postgres; } ||
         warn "Database did not start."
     fi
   fi

   exit "$failed"
   ```

4. Under Network access, add these hosts to Allowed domains, one per line. The Doppler hosts serve the CLI and the secrets; the others are the plugin MCP servers you use:

   ```text
   packages.doppler.com
   api.doppler.com
   mcp.asana.com
   mcp.atlassian.com
   mcp.datadoghq.com
   mcp.figma.com
   mcp.intercom.com
   mcp.linear.app
   mcp.notion.com
   mcp.pagerduty.com
   mcp.slack.com
   ```

`DOPPLER_TOKEN` is the read-only service token of `dev`; `doppler run` reads the other secrets through it, so the cloud environment holds no other credential. `MEDILAB_ODOO_IMAGE` makes `task up` run the image that `cd-core` publishes instead of building one: the build fails in a session, because its container does not trust the proxy's certificate. The image carries the Python packages of `main`; the modules come from the checkout. The setup script cannot read the environment variables; the Doppler CLI reads `DOPPLER_TOKEN` later, in the session. Install tools from package registries: `curl ... | sh` installers are refused in a session.

## Start a session

1. Check the branch with `git status` and `git log --oneline -3`. If its pull request is already merged, restart the branch from `origin/main`.
2. Read `AGENTS.md`, then `docs/readme.md`, and activate the project in Serena.
3. If the setup script did not run `task ai:setup`, install `task` with `uv tool install go-task-bin`, then run `task ai:setup` and `task ai:verify`. The `odoo` MCP server works right after, in the same session.
4. Run `git fetch --unshallow origin main` before `git log -S` or `git blame`: the clone is shallow.

## Run the app

1. If `docker info` fails, the setup script did not start Docker: run the Docker lines of the setup script.
2. Run `task up`. It starts the database, Garage, CloudBeaver and Odoo at `http://localhost:8069`, which the built-in Chromium opens. A new database holds no modules until they are installed.

The database listens on `localhost:15432` with user and password `root`. When it was not up at session start, the `postgres` MCP server has already failed; query the database with `PGPASSWORD=root psql -h localhost -p 15432 -U root -d medilab`.

## Limits

| Limit                              | What to do                                                                      |
| ---------------------------------- | ------------------------------------------------------------------------------- |
| The container is deleted when idle | Commit and push before leaving                                                  |
| A tool a session installs is gone  | Add it to the setup script                                                      |
| A host is refused by the proxy     | Allow it under Network access, or attach your own computer with Remote Control  |
| Production cannot be reached       | Reproduce locally, or give the exact URLs or queries to someone with access     |
| No `gh` CLI                        | Use the GitHub MCP tools for issues, pull requests, comments and CI             |
| The disk allowance runs out        | Delete build artifacts, Docker images and caches; deletes work when writes fail |
| One branch per session             | Work and push only on the session's `claude/...` branch                         |

## Related documents

- [Secrets](../infrastructure/secrets.md)
- [Odoo intelligence](odoo-intelligence.md)
- [Taskfile conventions](../conventions/taskfiles.md)
- [Claude Code cloud environments](https://code.claude.com/docs/en/cloud-environments)
