# Taskfile conventions

How the [Task](https://taskfile.dev) commands in this repository are written, and how they print to the terminal.

## File structure

```text
taskfile.yml                    entrypoint: includes the taskfiles, defines setup
tools/
├── ansible/                    Ansible image, its compose file and the entrypoint that loads the SSH key
├── odoo-intelligence/          Shared OdooLS MCP bridge, local installer, Serena launcher and tests
├── taskfiles/
│   ├── ai.taskfile.yml         AI tooling: local Serena, OdooLS, source mirror, verification and isolated Cursor setup
│   ├── ansible.taskfile.yml    Ansible in a container: ping, inspect, check, apply, kubeconfig, lint
│   ├── app.taskfile.yml        run the app: up, stop, restart, logs, upgrade, reset
│   ├── dev.taskfile.yml        developer setup and checks: doppler, venv, Odoo source, lint, typecheck
│   ├── test.taskfile.yml       tests: core, uninstall, typecheck, e2e, apps
│   └── tf.taskfile.yml         Terraform: setup, init, plan, apply, output
├── typecheck/                  pyright runner, the links of the addons into the Odoo source, and their tests
└── scripts/                    scripts the tasks run, see Scripts
    ├── log.sh                  output helpers sourced by the tasks
    ├── doppler.sh              Doppler login helper sourced by the tasks
    ├── ai_setup.sh             ai:setup prerequisites and environment
    ├── odoo_source.sh          dev:odoo-source download and sparse checkout
    ├── compose_down.sh         task stop and task reset: drop containers left on the project network, then compose down
    ├── compose_env.py          dev:compose-env: this checkout's compose project in tools/infrastructure/.env
    ├── odoo_upgrade.sh         task upgrade: one-shot module install, then fail when that run logs a warning
    ├── run_strict.sh           run a command and fail when its output contains a warning
    ├── test_apps.sh            test:apps
    ├── test_shards.py          splits the Odoo test classes into shards for test:core
    └── test_core_*.sh          test:core steps run inside a container
```

- `taskfile.yml` includes each taskfile with `dir: .` and `flatten: true`, so every task runs from the repository root and is called without a prefix: `task up`, not `task app:up`.
- A new group of tasks gets its own `tools/taskfiles/<group>.taskfile.yml`, included the same way.
- The `env:` block of an included taskfile applies to the tasks of every taskfile, and when two taskfiles set the same variable, which value a task gets changes from run to run. Set a variable there only to the value every taskfile uses, such as `COMPOSE_FILE` for the local infrastructure; a task that needs another compose file names it with `docker compose -f`, as the Ansible tasks do.
- Shell code shared by several tasks goes in `tools/scripts/`, not copied between tasks.
- `task up` and `task reset` set `BUILDAH_FORMAT=docker` on the image build only. That format is what lets Podman keep the base image shell. It stays off the taskfile `env:` block, which would apply it to every task.
- `run_strict.sh` fails a command when its output contains a warning. `task upgrade` sources it, along with `odoo_upgrade.sh`, so the check runs in Task's shell on Linux and Windows. Color codes around the log level are ignored, so a colored warning still fails the command.

## Tasks

- Every task a developer runs has a `desc`, so it appears in `task --list`. Write it as an instruction: "Restart Odoo after changing modules or config".
- Values used by more than one command, such as versions, paths and project names, are `vars` at the top of the taskfile, not literals inside the commands.
- Set `silent: true` on tasks that print their own messages, so Task does not echo every command.
- Set `interactive: true` on a task that reads input.
- Give a task that can be skipped when already done a `status` check, as `doppler` has.
- Prefer a long, readable name with a short alias: `reset` with `aliases: [wipe]`.

## Shell

- Task runs commands in its built-in shell, which understands Bash syntax on every platform, including Windows without Git Bash. Do not rely on programs that are missing from a plain Windows install.
- A program started through a wrapper such as `doppler run -- <program>` runs directly, not in a shell, so shell builtins and Unix tools like `env` fail on Windows. Set its environment with the taskfile's `env:` block.
- Use `printf`, not `echo -e`; it behaves the same in every shell.
- A multi-line command starts with `set -e` when a failed step must stop the task.
- Check that an external tool exists before using it, and say how to install it when it does not.
- Turn off the progress output of noisy tools (`git --quiet`, `-c advice.detachedHead=false`) and print one line about what is happening instead. Keep their errors visible.

## Scripts

A command longer than ten lines goes into a script in `tools/scripts/`, and the task runs the script instead of holding the code.

- Name the script after its task: `odoo_source.sh` for `dev:odoo-source`. Split a task with several long steps into one script per step: `test_core_install.sh`, `test_core_shard.sh`.
- The first lines of a script say what it does, where it runs, and its usage or the environment variables it needs.
- Pass values from the taskfile as arguments or environment variables; the taskfile keeps the `vars`, the script holds no copies of them.
- A script for the host is sourced, so it runs in Task's built-in shell on every platform: `. tools/scripts/odoo_source.sh {{.ODOO_SOURCE_DIR}} {{.ODOO_SOURCE_REVISION}}`. It loads `log.sh` itself and starts with `set -e` when a failed step must stop it.
- A script for the Odoo container runs with `bash`; the `odoo` service mounts `tools/scripts` read-only at `/opt/medilab/scripts`: `docker compose run --rm -T -e SHARD=1 --entrypoint bash odoo /opt/medilab/scripts/test_core_shard.sh`. Do not pipe a script into `bash -s`; a command that reads standard input swallows the rest of the script.
- Code shared by several scripts goes in a script they source, such as `test_core_common.sh`.
- SonarQube scans the scripts: test with `[[ ]]`, end every function with an explicit `return`, and install packages with `--only-binary :all:` for pip and `--ignore-scripts` for bun and npm.
- `.gitattributes` keeps `*.sh` files at LF line endings on every checkout, because bash in the container fails on CRLF.

## Output

Tasks print their own messages through the helpers in `tools/scripts/log.sh`. Load them at the start of the command with the `LOG` variable, then call them:

```yaml
vars:
  LOG: tools/scripts/log.sh

tasks:
  example:
    silent: true
    cmds:
      - |
        . {{.LOG}}
        log_step "Odoo source"
        log_info "Downloading Odoo 20.0. This takes a minute."
        log_ok "Odoo source ready in .local/odoo-source."
```

| Helper                    | Use for                             | Prints                                     |
| ------------------------- | ----------------------------------- | ------------------------------------------ |
| `log_step "<title>"`      | The start of each section of a task | Blank line, then bold cyan `==>` and title |
| `log_info "<text>"`       | Detail about what is happening      | Dimmed, indented line                      |
| `log_option <n> "<text>"` | One choice in a menu                | Indented line with a cyan `n)`             |
| `log_prompt "<question>"` | A question before `read`            | Yellow `?`, no line break                  |
| `log_ok "<text>"`         | The result of a task that succeeded | Green `[COMPLETED]`                        |
| `log_error "<text>"`      | A failure, followed by `exit 1`     | Red `[ERROR]`, to stderr                   |
| `log_link "<name>" <url>` | An address the developer opens      | Aligned name and underlined URL            |

- A task that runs several steps or asks questions opens with `log_step`. A task that finishes something the developer waits for ends with `log_ok`. A task that only calls other tasks or one tool prints nothing itself.
- Write messages as short sentences ending with a full stop. An error says what failed and what to do next: "doppler not found. Install: winget install Doppler.doppler".
- Do not write color escape codes in the taskfiles; add a helper to `log.sh` when a new kind of line is needed.
- Setting `NO_COLOR=1` prints every helper without colors, for logs and CI. Odoo follows the same variable and leaves its log level uncolored.

## Related documents

- [Python](python.md)
- [Documentation](documentation.md)
