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
3. Paste this under Setup script. It installs the Doppler CLI and `task`, and when the repository is already cloned, runs `task ai:setup` and pre-installs the `postgres` MCP server so it starts within its 30-second limit.

   ```bash
   #!/bin/bash
   set -euo pipefail

   # Doppler CLI from its signed apt repository
   curl -sLf --retry 3 'https://packages.doppler.com/public/cli/gpg.DE2A7741A397C129.key' \
     | gpg --dearmor --yes -o /usr/share/keyrings/doppler-archive-keyring.gpg
   echo "deb [signed-by=/usr/share/keyrings/doppler-archive-keyring.gpg] https://packages.doppler.com/public/cli/deb/debian any-version main" \
     > /etc/apt/sources.list.d/doppler-cli.list
   apt-get update -o Dir::Etc::sourcelist=sources.list.d/doppler-cli.list -o Dir::Etc::sourceparts=- -qq
   apt-get install -y -qq doppler

   # Task runner for the repository's taskfiles
   uv tool install go-task-bin
   export PATH="$HOME/.local/bin:$PATH"

   repo=/home/user/medilab
   if [ -d "$repo" ]; then
     cd "$repo"
     task ai:setup
     uvx --python 3.13 --overrides tools/odoo-intelligence/postgres-overrides.txt \
       --with "mcp<2" postgres-mcp==0.3.0 --help > /dev/null
   fi
   ```

4. Under Network access, allow `pkg-containers.githubusercontent.com` so the Odoo image build can pull `ghcr.io/astral-sh/uv`, and the hosts of any plugin MCP server you use.

`DOPPLER_TOKEN` is the read-only service token of `dev`; `doppler run` reads the other secrets through it, so the cloud environment holds no other credential. The setup script cannot read the environment variables; the Doppler CLI reads `DOPPLER_TOKEN` later, in the session. Install tools from package registries: `curl ... | sh` installers are refused in a session.

## Start a session

1. Check the branch with `git status` and `git log --oneline -3`. If its pull request is already merged, restart the branch from `origin/main`.
2. Read `AGENTS.md`, then `docs/readme.md`, and activate the project in Serena.
3. If the setup script did not run `task ai:setup`, install `task` with `uv tool install go-task-bin`, then run `task ai:setup` and `task ai:verify`. The `odoo` MCP server works right after, in the same session.
4. Run `git fetch --unshallow origin main` before `git log -S` or `git blame`: the clone is shallow.

## Run the app

1. Start the Docker daemon, which is installed but not running: `dockerd > /tmp/dockerd.log 2>&1 &`, then check with `docker info`.
2. Run `task dev:compose-env`, then `cd tools/infrastructure && docker compose up -d postgres` for the database alone. It listens on `localhost:15432` with user and password `root`. Add `garage garage-setup odoo` and `--build` for the app at `http://localhost:8069`, which the built-in Chromium opens.

Docker Hub can answer `429 Too Many Requests`; retry after 15 to 30 seconds. The `postgres` MCP server connects only when the database is up at session start, which it is not in a new container; query the database with `PGPASSWORD=root psql -h localhost -p 15432 -U root -d medilab` instead.

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
