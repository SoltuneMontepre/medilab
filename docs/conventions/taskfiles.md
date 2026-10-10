# Taskfile conventions

How the [Task](https://taskfile.dev) commands in this repository are written, and how they print to the terminal.

## File structure

```text
taskfile.yml                    entrypoint: includes the taskfiles, defines setup
tools/
├── serena-odoo-ls/             OdooLS adapter that Serena loads as the `odoo` language server
├── taskfiles/
│   ├── ai.taskfile.yml         AI tooling: the npx check for the MCP servers, Serena with the OdooLS adapter, OdooLS download
│   ├── app.taskfile.yml        run the app: up, stop, restart, logs, upgrade, reset
│   ├── dev.taskfile.yml        developer setup and checks: doppler, venv, Odoo source, lint
│   ├── test.taskfile.yml       tests: core, e2e, apps
│   └── tf.taskfile.yml         Terraform: setup, init, plan, apply, output
└── scripts/
    ├── log.sh                  output helpers sourced by the tasks
    └── doppler.sh              Doppler login helper sourced by the tasks
```

- `taskfile.yml` includes each taskfile with `dir: .` and `flatten: true`, so every task runs from the repository root and is called without a prefix: `task up`, not `task app:up`.
- A new group of tasks gets its own `tools/taskfiles/<group>.taskfile.yml`, included the same way.
- Shell code shared by several tasks goes in `tools/scripts/`, not copied between tasks.

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
        log_info "Downloading Odoo 19.0. This takes a minute."
        log_ok "Odoo source ready in .local/odoo-source."
```

| Helper                    | Use for                                 | Prints                                     |
| ------------------------- | --------------------------------------- | ------------------------------------------ |
| `log_step "<title>"`      | The start of each section of a task     | Blank line, then bold cyan `==>` and title |
| `log_info "<text>"`       | Detail about what is happening          | Dimmed, indented line                      |
| `log_option <n> "<text>"` | One choice in a menu                    | Indented line with a cyan `n)`             |
| `log_prompt "<question>"` | A question before `read`                | Yellow `?`, no line break                  |
| `log_ok "<text>"`         | The result of a task that succeeded     | Green `[COMPLETED]`                        |
| `log_error "<text>"`      | A failure, followed by `exit 1`         | Red `[ERROR]`, to stderr                   |
| `log_link "<name>" <url>` | An address the developer opens          | Aligned name and underlined URL            |

- A task that runs several steps or asks questions opens with `log_step`. A task that finishes something the developer waits for ends with `log_ok`. A task that only calls other tasks or one tool prints nothing itself.
- Write messages as short sentences ending with a full stop. An error says what failed and what to do next: "doppler not found. Install: winget install Doppler.doppler".
- Do not write color escape codes in the taskfiles; add a helper to `log.sh` when a new kind of line is needed.
- Setting `NO_COLOR=1` prints every helper without colors, for logs and CI.

## Related documents

- [Python](python.md)
- [Documentation](documentation.md)
