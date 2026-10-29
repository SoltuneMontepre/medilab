# Office documents

How the `.docx`, `.xlsx` and `.pptx` files in `docs/`, such as the backlog in `docs/reports`, are read and edited by people and agents. Only those who work on these files need this setup.

## Setup

```sh
task docs:setup
```

It checks that `officecli --version` matches the version pinned in `tools/taskfiles/docs.taskfile.yml`. If OfficeCLI is absent, it installs [OfficeCLI](https://github.com/iOfficeAI/OfficeCLI) globally with npm; the first run downloads the binary of that tag and checks its SHA256. An installed version that differs fails setup: install the pinned npm package and ensure it is first on PATH. `task setup` does not run it.

## Use

Agents use the `officecli` skill in `.agents/skills/officecli/`, derived from the upstream `SKILL.md` of the pinned tag with local installation and usage corrections. Claude Code loads it through `.claude/skills/officecli/`. It runs `officecli` in the shell; no MCP server is configured for it.

- Read before editing: `officecli view <file> outline` lists the sheets, slides or headings; `officecli view <file> text` prints the content.
- Close the file in the corresponding application (Excel, Word, PowerPoint, or WPS) before using OfficeCLI. After editing with OfficeCLI, run `officecli save <file>` or `officecli close <file>` before opening it in the application.
- When changing the pinned version, copy the upstream `SKILL.md` of the same tag into `.agents/skills/officecli/` and reapply the local installation and usage corrections, including Markdown table escaping.

## Related documents

- [Taskfiles](../conventions/taskfiles.md)
- [Documentation](../conventions/documentation.md)
