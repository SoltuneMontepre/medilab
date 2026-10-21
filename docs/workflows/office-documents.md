# Office documents

How the `.docx`, `.xlsx` and `.pptx` files in `docs/`, such as the backlog in `docs/reports`, are read and edited by people and agents. Only those who work on these files need this setup.

## Setup

```sh
task docs:setup
```

It installs [OfficeCLI](https://github.com/iOfficeAI/OfficeCLI) globally with npm at the version pinned in `tools/taskfiles/docs.taskfile.yml`, unless `officecli` is already on PATH. Its first run downloads the binary of that tag and checks its SHA256. `task setup` does not run it.

## Use

Agents use the `officecli` skill: the upstream `SKILL.md` of the pinned tag in `.agent/skills/officecli/`, which Claude Code loads through `.claude/skills/officecli/`. It runs `officecli` in the shell; no MCP server is configured for it.

- Read before editing: `officecli view <file> outline` lists the sheets, slides or headings; `officecli view <file> text` prints the content.
- Close the file in Excel, Word or PowerPoint first. An open file is locked, and OfficeCLI cannot read or write it.
- Changing the pinned version means copying the upstream `SKILL.md` of the same tag into `.agent/skills/officecli/`.

## Related documents

- [Taskfiles](../conventions/taskfiles.md)
- [Documentation](../conventions/documentation.md)
