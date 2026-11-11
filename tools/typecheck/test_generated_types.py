"""Generated interfaces must detect bad members and calls while checking source method bodies."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from generate_types import render

ROOT = Path(__file__).resolve().parents[2]


def field(kind, comodel=None):
    return {"type": kind, "comodel": comodel, "required": False, "related": None}


class TestGeneratedTypes(unittest.TestCase):
    def registry(self):
        return {
            "probe": {
                "fields": {
                    "name": field("char"),
                    "partner_id": field("many2one", "partner"),
                },
                "methods": {
                    "label": {"module": "odoo.addons.typing_fixture", "class": "Probe"}
                },
            },
            "partner": {"fields": {"name": field("char")}, "methods": {}},
        }

    def test_unknown_relation_and_field_types_fail_generation(self):
        for invalid in (field("many2one", "missing"), field("unsupported")):
            with self.subTest(field=invalid):
                registry = self.registry()
                registry["probe"]["fields"]["invalid"] = invalid
                with self.assertRaises(ValueError):
                    render(registry)

    def test_unresolved_placeholder_relations_are_rejected(self):
        registry = self.registry()
        registry["_unknown"] = {"fields": {}, "methods": {}}
        registry["probe"]["fields"]["partner_id"] = field("many2one", "_unknown")
        with self.assertRaisesRegex(ValueError, "Unknown relation target"):
            render(registry)

    def test_output_is_independent_of_registry_insertion_order(self):
        registry = self.registry()
        self.assertEqual(
            render(registry), render(dict(reversed(list(registry.items()))))
        )

    def check(self, expression, body="return (self.name or '') * count"):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            source = directory / "odoo/addons/typing_fixture/__init__.py"
            source.parent.mkdir(parents=True)
            source.write_text(
                "from typing import TYPE_CHECKING\n"
                "if TYPE_CHECKING:\n"
                "    from medilab_model_types import Model_probe as ModelBase\n"
                "else:\n"
                "    from odoo.models import Model as ModelBase\n"
                "class Probe(ModelBase):\n"
                "    def label(self, count: int) -> str:\n"
                f"        {body}\n",
                encoding="utf-8",
            )
            (directory / "medilab_model_types.pyi").write_text(
                render(self.registry()), encoding="utf-8"
            )
            (directory / "medilab_model_types.py").write_text(
                'raise RuntimeError("Types only")\n'
            )
            case = directory / "case.py"
            case.write_text(
                "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from medilab_model_types import Model_probe\n"
                + expression,
                encoding="utf-8",
            )
            config = directory / "pyrightconfig.json"
            config.write_text(
                json.dumps(
                    {
                        "include": [
                            "odoo/addons/typing_fixture/__init__.py",
                            "case.py",
                            "medilab_model_types.pyi",
                        ],
                        "stubPath": str(directory),
                        "extraPaths": [
                            str(directory),
                            str(ROOT / ".local/odoo-source"),
                        ],
                        "venvPath": str(ROOT / "src/core"),
                        "venv": ".venv",
                        "typeCheckingMode": "basic",
                    }
                ),
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pyright",
                    "--outputjson",
                    "--project",
                    str(config),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        report = json.loads(result.stdout)
        self.assertGreaterEqual(report["summary"]["filesAnalyzed"], 2)
        return report["generalDiagnostics"]

    def test_fields_relations_and_source_methods_pass(self):
        diagnostics = self.check(
            "def controller(record: Model_probe) -> str:\n"
            "    return record.label(2) + (record.partner_id.name or '')\n"
        )
        self.assertEqual(diagnostics, [])

    def test_unknown_field_and_method_are_rejected(self):
        for expression in (
            "record.missing",
            "record.missing()",
            "record.partner_id.missing",
        ):
            with self.subTest(expression=expression):
                diagnostics = self.check(
                    f"def controller(record: Model_probe):\n    return {expression}\n"
                )
                self.assertTrue(
                    any(
                        d.get("rule") == "reportAttributeAccessIssue"
                        for d in diagnostics
                    ),
                    diagnostics,
                )

    def test_wrong_method_argument_is_rejected(self):
        diagnostics = self.check(
            "def controller(record: Model_probe):\n    return record.label('wrong')\n"
        )
        self.assertTrue(
            any(d.get("rule") == "reportArgumentType" for d in diagnostics), diagnostics
        )

    def test_source_method_bodies_are_checked(self):
        diagnostics = self.check("", body="return self.missing")
        self.assertTrue(
            any(d.get("rule") == "reportAttributeAccessIssue" for d in diagnostics),
            diagnostics,
        )

    def test_unbound_methods_keep_the_explicit_record_argument(self):
        diagnostics = self.check(
            "def controller(record: Model_probe):\n    return Model_probe.label(record, 2)\n"
        )
        self.assertEqual(diagnostics, [])

    def test_wrong_field_value_is_rejected(self):
        diagnostics = self.check(
            "def controller(record: Model_probe):\n    record.name = 42\n"
        )
        self.assertTrue(
            any(d.get("rule") == "reportAttributeAccessIssue" for d in diagnostics),
            diagnostics,
        )


if __name__ == "__main__":
    unittest.main()
