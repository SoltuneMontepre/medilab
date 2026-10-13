"""Launch the tooling belonging to this script's worktree, from any working directory."""

import os
import shutil
import sys
from pathlib import Path

project = Path(__file__).resolve().parent
uv = shutil.which("uv")
if uv is None:
    raise SystemExit("uv not found. Install https://docs.astral.sh/uv/ and run task ai:setup.")
os.execv(uv, [uv, "run", "--locked", "--project", str(project), "medilab-odoo", *sys.argv[1:]])
