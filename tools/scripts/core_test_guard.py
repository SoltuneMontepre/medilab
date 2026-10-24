"""Own the temporary databases and filestore directory used by task test:core.

Usage: core_test_guard.py prepare|clone|clean
TEST_DB and SHARD_NUMBERS come from the Taskfile. An interrupted run leaves its
marker and refuses a new run until its resources have been reviewed.
"""

import json
import os
import re
import subprocess
import sys

from demo_bootstrap import ROOT
from local_compose import _resolve

MARKERS = ROOT / ".local/core-test-runs"


class CoreTestError(RuntimeError):
    pass


def _database_names(database, app_database, shard_numbers):
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,48}", database):
        raise CoreTestError("TEST_DB must be a PostgreSQL-safe lowercase name.")
    shards = shard_numbers.split()
    if not shards or any(
        not re.fullmatch(r"[1-9]\d?", shard, re.ASCII) for shard in shards
    ):
        raise CoreTestError("SHARD_NUMBERS must contain positive shard numbers.")
    if len(shards) != len(set(shards)):
        raise CoreTestError("SHARD_NUMBERS contains a duplicate shard.")
    names = (database, *(f"{database}_{shard}" for shard in shards))
    if app_database in names or database in {"postgres", "template0", "template1"}:
        raise CoreTestError(
            "TEST_DB cannot name the application database or a system database."
        )
    if any(len(name) > 63 for name in names):
        raise CoreTestError(
            "A test database name exceeds PostgreSQL's identifier limit."
        )
    return names


def _run_directory(database):
    return f"/var/lib/odoo/{database}-run"


def _compose(context, *arguments):
    project, _marker, files, environment = context
    return subprocess.run(
        ["docker", "compose", "-p", project, *files, *arguments],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _database_exists(context, database):
    user = context[3].get("MEDILAB_DB_USER", "root")
    result = _compose(
        context,
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        user,
        "-d",
        "postgres",
        "-Atqc",
        f"SELECT 1 FROM pg_database WHERE datname = '{database}'",
    )
    if result.returncode:
        raise CoreTestError(
            "Could not inspect PostgreSQL test databases; refusing test setup."
        )
    return result.stdout.strip() == "1"


def _run_directory_exists(context, directory):
    result = _compose(
        context,
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "--entrypoint",
        "/usr/bin/test",
        "odoo",
        "-e",
        directory,
    )
    if result.returncode not in (0, 1):
        raise CoreTestError(
            "Could not inspect the Odoo test directory; refusing test setup."
        )
    return result.returncode == 0


def _selection():
    context = _resolve("exec")
    database = os.environ.get("TEST_DB", "")
    names = _database_names(
        database,
        context[3].get("MEDILAB_DB_NAME", "medilab"),
        os.environ.get("SHARD_NUMBERS", ""),
    )
    if os.environ.get("TEST_RUN_DIR") != _run_directory(database):
        raise CoreTestError("TEST_RUN_DIR does not match the selected test database.")
    project, marker, _files, _environment = context
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", project):
        raise CoreTestError("The selected Compose project has an unsafe name.")
    path = MARKERS / f"{project}-{database}.json"
    state = {
        "database": database,
        "names": names,
        "owner": marker.get("owner") if marker else None,
        "project": project,
        "run_directory": _run_directory(database),
        "worktree": str(ROOT),
    }
    return context, path, state


def _require_marker(path, expected):
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CoreTestError("No readable test-run ownership marker exists.") from error
    if saved != {**expected, "names": list(expected["names"])}:
        raise CoreTestError(
            "Test-run ownership differs from the current Compose selection."
        )


def prepare():
    context, path, state = _selection()
    if path.exists():
        raise CoreTestError(
            "A test-run marker already exists; review it before starting another run."
        )
    for database in state["names"]:
        if _database_exists(context, database):
            raise CoreTestError(
                f"Test database {database!r} already exists; refusing to overwrite it."
            )
    if _run_directory_exists(context, state["run_directory"]):
        raise CoreTestError(
            "The Odoo test directory already exists; refusing to overwrite it."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        json.dump(state, output, indent=2, sort_keys=True)
        output.write("\n")


def clone():
    context, path, state = _selection()
    _require_marker(path, state)
    if not _database_exists(context, state["database"]):
        raise CoreTestError(
            "The installed test database is missing; refusing to clone shards."
        )
    user = context[3].get("MEDILAB_DB_USER", "root")
    for database in state["names"][1:]:
        if _database_exists(context, database):
            raise CoreTestError(f"Test shard database {database!r} already exists.")
        result = _compose(
            context,
            "exec",
            "-T",
            "postgres",
            "createdb",
            "-U",
            user,
            "-T",
            state["database"],
            database,
        )
        if result.returncode:
            raise CoreTestError(f"Could not create test shard database {database!r}.")


def clean():
    context, path, state = _selection()
    _require_marker(path, state)
    user = context[3].get("MEDILAB_DB_USER", "root")
    for database in reversed(state["names"]):
        result = _compose(
            context,
            "exec",
            "-T",
            "postgres",
            "dropdb",
            "-U",
            user,
            "--if-exists",
            database,
        )
        if result.returncode:
            raise CoreTestError(
                f"Could not remove owned test database {database!r}; marker retained."
            )
    result = _compose(
        context,
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "--user",
        "root",
        "--entrypoint",
        "rm",
        "odoo",
        "-rf",
        state["run_directory"],
    )
    if result.returncode:
        raise CoreTestError(
            "Could not remove the owned Odoo test directory; marker retained."
        )
    path.unlink()


def main():
    commands = {"prepare": prepare, "clone": clone, "clean": clean}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        raise SystemExit("Usage: core_test_guard.py prepare|clone|clean")
    try:
        commands[sys.argv[1]]()
    except (CoreTestError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
