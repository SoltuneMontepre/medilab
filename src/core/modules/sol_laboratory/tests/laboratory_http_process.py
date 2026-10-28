import sys
from pathlib import Path

MODULES = Path(__file__).resolve().parents[2]


def odoo_command(tracing=None):
    """Trace the independent HTTP worker into the parent's parallel coverage data when enabled."""
    command = [sys.executable]
    if tracing is not None:
        command.extend(["-m", "coverage", "run", "--parallel-mode", "--data-file", tracing.get_option("run:data_file")])
        if tracing.get_option("run:branch"):
            command.append("--branch")
        for option in ("source", "omit"):
            values = tracing.get_option(f"run:{option}")
            if values:
                if option == "source":
                    values = [str(MODULES / value) if (MODULES / value).is_dir() else value for value in values]
                command.extend([f"--{option}", ",".join(values)])
    return [*command, "-m", "odoo"]
