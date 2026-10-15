"""task typecheck resolves odoo.addons imports through links, and still fails on missing names and type errors."""

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULES = ROOT / "src" / "core" / "modules"
ODOO_ADDONS = ROOT / ".local" / "odoo-source" / "odoo" / "addons"
TYPECHECK = Path(__file__).with_name("typecheck.py")


class TestTypecheck(unittest.TestCase):
    def typecheck(self, source):
        """The exit code and output of the typecheck of a file holding source."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "case.py")
            path.write_text(textwrap.dedent(source), encoding="utf-8")
            result = subprocess.run([sys.executable, TYPECHECK, path], capture_output=True, text=True, check=False)
        return result.returncode, result.stdout + result.stderr

    def assert_passes(self, source):
        code, output = self.typecheck(source)
        self.assertEqual(code, 0, output)

    def assert_fails(self, source, rule):
        code, output = self.typecheck(source)
        self.assertEqual(code, 1, output)
        self.assertIn("error: ", output)
        self.assertIn(rule, output)

    def test_each_module_is_linked_into_the_odoo_source(self):
        modules = [path for path in MODULES.iterdir() if (path / "__manifest__.py").is_file()]
        self.assertTrue(modules)
        for module in modules:
            with self.subTest(module=module.name):
                link = ODOO_ADDONS / module.name
                self.assertTrue(link.is_symlink() or link.is_junction(), f"{link} is not a link")
                self.assertTrue(link.samefile(module))

    def test_a_constant_of_a_module_resolves(self):
        self.assert_passes(
            """
            from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_PARAMETER

            NAME = MODEL_TEST_PARAMETER
            """
        )

    def test_a_missing_name_of_a_module_fails(self):
        self.assert_fails(
            """
            from odoo.addons.sol_laboratory.constants.models import (
                MODEL_TEST_PARAMETER,
                MODEL_UNKNOWN,
            )

            NAMES = (MODEL_TEST_PARAMETER, MODEL_UNKNOWN)
            """,
            "MODEL_UNKNOWN",
        )

    def test_a_missing_module_fails(self):
        self.assert_fails(
            "from odoo.addons.sol_unknown.constants.models import MODEL_UNKNOWN\n", "reportMissingImports"
        )

    def test_a_type_error_fails(self):
        self.assert_fails('COUNT: int = "one"\n', "reportAssignmentType")

    def test_a_wrong_call_fails(self):
        self.assert_fails(
            """
            from odoo.addons.sol_laboratory.services.request_env import request_env

            request_env("medilab")
            """,
            "reportCallIssue",
        )

    def test_odoo_dynamic_models_pass(self):
        self.assert_passes(
            """
            from odoo import fields, models
            from odoo.fields import Command
            from odoo.tests import TransactionCase


            class Partner(models.Model):
                _inherit = "res.partner"

                kind = fields.Selection(selection=[("lab", "Laboratory")])

                def _first_user_login(self):
                    return self.env["res.users"].search([], limit=1).login

                def _tag(self, category):
                    self.write({"category_id": [Command.link(category.id)]})


            class TestPartner(TransactionCase):
                def test_reading_a_field_needs_access(self):
                    with self.assertRaises(ValueError):
                        self.env["res.partner"].kind
            """
        )


if __name__ == "__main__":
    unittest.main()
