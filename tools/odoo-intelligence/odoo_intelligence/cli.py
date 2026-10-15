"""Worktree-local entry points; no global tool installation or config mutation."""

import argparse
import os
from pathlib import Path

from .workspace import PACKAGE_ROOT, Workspace


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["install", "mcp", "serena", "serena-hooks", "verify", "cursor-setup"])
    parser.add_argument("--root", type=Path, default=PACKAGE_ROOT.parents[1])
    args, remaining = parser.parse_known_args()
    root = args.root.resolve()
    if args.mode == "install":
        from .install import install

        install(root)
    elif args.mode == "mcp":
        from .server import create_server

        create_server(root).run(transport="stdio")
    elif args.mode in {"serena", "serena-hooks"}:
        from .prerequisites import terraform_directory

        os.environ["SERENA_HOME"] = str(root / ".local" / "serena")
        os.environ["PATH"] = str(terraform_directory(Workspace(root))) + os.pathsep + os.environ.get("PATH", "")
        os.chdir(root)
        if args.mode == "serena":
            from serena.cli import top_level

            top_level(args=remaining)
        else:
            from serena.hooks import hook_commands

            hook_commands(args=remaining)
    elif args.mode == "cursor-setup":
        from .prerequisites import install_cursor

        install_cursor(root)
    else:
        from .verify import verify

        verify(root)


if __name__ == "__main__":
    main()
