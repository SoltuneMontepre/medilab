"""The release's upgrade fingerprint: what changes it, and how it is read from and recorded in a database."""

import importlib.util
import io
import os
import secrets
import shutil
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = (
    Path(__file__).resolve().parents[3] / "infra/cluster/odoo/upgrade/fingerprint.py"
)
# The job's connection settings; the password is random, so none lives in the repository.
ENV = {
    "HOST": "medilab-db-rw",
    "USER": "medilab",
    "PASSWORD": secrets.token_urlsafe(12),
}


class FakeCursor:
    """Answers each query with the next of the given rows and keeps what was executed."""

    def __init__(self, rows):
        self.rows = list(rows)
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        self.executed.append((" ".join(query.split()), params))

    def fetchone(self):
        return self.rows.pop(0)


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return self._cursor


def load(cursor):
    psycopg2 = types.ModuleType("psycopg2")
    psycopg2.connect = mock.Mock(return_value=FakeConnection(cursor))
    with mock.patch.dict(sys.modules, {"psycopg2": psycopg2}):
        spec = importlib.util.spec_from_file_location("fingerprint", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module, psycopg2


class TestCompute(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        (self.root / "sol_laboratory").mkdir()
        (self.root / "sol_laboratory/models.py").write_text("x = 1\n")
        self.fingerprint, _ = load(FakeCursor([]))
        self.fingerprint.ROOTS = (str(self.root), str(self.root / "missing"))

    def compute(self, modules="sol_laboratory"):
        return self.fingerprint.compute(modules)

    def test_same_files_and_modules_give_the_same_fingerprint(self):
        self.assertEqual(self.compute(), self.compute())

    def test_changed_file_changes_it(self):
        before = self.compute()
        (self.root / "sol_laboratory/models.py").write_text("x = 2\n")

        self.assertNotEqual(self.compute(), before)

    def test_renamed_file_changes_it(self):
        before = self.compute()
        (self.root / "sol_laboratory/models.py").rename(
            self.root / "sol_laboratory/fields.py"
        )

        self.assertNotEqual(self.compute(), before)

    def test_other_modules_change_it(self):
        self.assertNotEqual(self.compute("sol_laboratory,sol_demo"), self.compute())

    def test_compiled_python_does_not_change_it(self):
        before = self.compute()
        (self.root / "sol_laboratory/__pycache__").mkdir()
        (self.root / "sol_laboratory/__pycache__/models.cpython-312.pyc").write_bytes(
            b"\0"
        )
        (self.root / "sol_laboratory/stray.pyc").write_bytes(b"\0")

        self.assertEqual(self.compute(), before)


class TestDatabase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, ENV)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_main(self, rows, *args):
        cursor = FakeCursor(rows)
        fingerprint, psycopg2 = load(cursor)
        output = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["fingerprint.py", *args]),
            redirect_stdout(output),
        ):
            fingerprint.main()
        return output.getvalue(), cursor, psycopg2

    def test_connects_with_the_job_credentials(self):
        _, _, psycopg2 = self.run_main([(False,)], "read", "medilab")

        psycopg2.connect.assert_called_once_with(
            host=ENV["HOST"],
            user=ENV["USER"],
            password=ENV["PASSWORD"],
            dbname="medilab",
        )

    def test_read_of_an_empty_database_is_empty(self):
        output, cursor, _ = self.run_main([(False,)], "read", "medilab")

        self.assertEqual(output, "\n")
        self.assertEqual(len(cursor.executed), 1)

    def test_read_without_a_recorded_fingerprint_is_empty(self):
        output, _, _ = self.run_main([(True,), None], "read", "medilab")

        self.assertEqual(output, "\n")

    def test_read_gives_the_recorded_fingerprint(self):
        output, cursor, _ = self.run_main([(True,), ("abc",)], "read", "medilab")

        self.assertEqual(output, "abc\n")
        self.assertEqual(cursor.executed[1][1], ["medilab.upgrade_fingerprint"])

    def test_installed_tells_whether_odoo_set_up_the_database(self):
        self.assertEqual(self.run_main([(True,)], "installed", "medilab")[0], "yes\n")
        self.assertEqual(self.run_main([(False,)], "installed", "medilab")[0], "no\n")

    def test_record_saves_or_replaces_the_fingerprint(self):
        output, cursor, _ = self.run_main([], "record", "medilab", "abc")

        self.assertEqual(output, "")
        query, params = cursor.executed[0]
        self.assertIn("ON CONFLICT (key) DO UPDATE", query)
        self.assertEqual(params, ["medilab.upgrade_fingerprint", "abc"])

    def test_compute_prints_the_fingerprint(self):
        cursor = FakeCursor([])
        fingerprint, _ = load(cursor)
        fingerprint.ROOTS = ()
        output = io.StringIO()
        with (
            mock.patch.object(sys, "argv", ["fingerprint.py", "compute", "sol_demo"]),
            redirect_stdout(output),
        ):
            fingerprint.main()

        self.assertEqual(output.getvalue(), fingerprint.compute("sol_demo") + "\n")

    def test_unknown_command_exits_with_the_usage(self):
        with self.assertRaises(SystemExit) as exit_:
            self.run_main([], "drop", "medilab")

        self.assertIn("Usage:", str(exit_.exception.code))


if __name__ == "__main__":
    unittest.main()
