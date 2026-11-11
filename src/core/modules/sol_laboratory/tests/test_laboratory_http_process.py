import sys
from pathlib import Path
from unittest.mock import Mock

from odoo.tests import BaseCase, tagged

from .laboratory_http_process import odoo_command


@tagged("post_install", "-at_install")
class TestLaboratoryHttpProcess(BaseCase):
    def test_native_http_worker_keeps_the_normal_odoo_launcher(self):
        self.assertEqual(odoo_command(), [sys.executable, "-m", "odoo"])

    def test_coverage_worker_saves_parallel_data_with_the_parent_sources(self):
        settings = {
            "run:data_file": "/owned/coverage/.coverage",
            "run:branch": True,
            "run:source": ["sol_laboratory", "sol_commerce"],
            "run:omit": ["*/tests/*"],
        }
        tracing = Mock()
        tracing.get_option.side_effect = settings.__getitem__

        command = odoo_command(tracing)

        self.assertEqual(command[:4], [sys.executable, "-m", "coverage", "run"])
        self.assertIn("--parallel-mode", command)
        self.assertIn("--branch", command)
        self.assertEqual(command[command.index("--data-file") + 1], settings["run:data_file"])
        sources = command[command.index("--source") + 1].split(",")
        self.assertTrue(all(Path(source).is_absolute() for source in sources))
        self.assertEqual([Path(source).name for source in sources], ["sol_laboratory", "sol_commerce"])
        self.assertEqual(command[command.index("--omit") + 1], "*/tests/*")
        self.assertEqual(command[-2:], ["-m", "odoo"])

    def test_coverage_worker_accepts_unrestricted_parent_sources(self):
        tracing = Mock()
        tracing.get_option.side_effect = {
            "run:data_file": "/owned/.coverage",
            "run:branch": False,
            "run:source": None,
            "run:omit": [],
        }.__getitem__

        command = odoo_command(tracing)

        self.assertNotIn("--source", command)
        self.assertNotIn("--omit", command)
        self.assertNotIn("--branch", command)
