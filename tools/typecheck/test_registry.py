"""Registry export does not invoke business methods; cleanup only removes owned resources."""

import json
import subprocess
import unittest
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import patch

from prepare_registry import OWNER_LABEL, remove_owned
from registry_export import default_type, export_registry


class TestRegistry(unittest.TestCase):
    def test_default_types_do_not_execute_default_functions(self):
        def business_default(model):
            raise AssertionError(
                "Default functions must not be executed during type generation."
            )

        self.assertEqual(
            default_type(SimpleNamespace(default=business_default)), "object"
        )
        self.assertEqual(default_type(SimpleNamespace(default=None)), "None")

    def test_odoo_constant_default_wrappers_preserve_the_value_type(self):
        def wrap(value):
            return lambda model: value

        for value, expected in ((7, "int"), (False, "Literal[False]"), ("text", "str")):
            wrapped = wrap(value)
            wrapped.__module__ = "odoo.orm.fields"
            wrapped.__qualname__ = "Field._setup_attrs__.<locals>.<lambda>"
            self.assertEqual(default_type(SimpleNamespace(default=wrapped)), expected)

    def test_export_preserves_inherited_fields_and_method_signatures(self):
        class Parent:
            _inherits: ClassVar = {"res.partner": "partner_id"}
            _fields: ClassVar = {
                "name": SimpleNamespace(type="char", required=False, related=None),
                "partner_id": SimpleNamespace(
                    type="many2one",
                    required=True,
                    related=None,
                    comodel_name="res.partner",
                ),
            }

            def business(self, value: int) -> str:
                raise AssertionError("The exporter must not call business methods.")

        class Child(Parent):
            pass

        class Environment:
            registry = ("probe",)

            def __getitem__(self, key):
                return Child()

        snapshot = export_registry(Environment())["probe"]
        self.assertIsNone(snapshot["fields"]["name"]["comodel"])
        self.assertEqual(snapshot["fields"]["partner_id"]["comodel"], "res.partner")
        self.assertEqual(snapshot["inherits"], {"res.partner": "partner_id"})
        self.assertEqual(
            snapshot["methods"]["business"]["signature"], "(self, value: int) -> str"
        )

    def test_cleanup_refuses_mismatched_owner(self):
        with (
            patch(
                "prepare_registry.run",
                return_value=subprocess.CompletedProcess([], 0, '[{"Labels":{}}]'),
            ) as run,
            self.assertRaisesRegex(RuntimeError, "unowned"),
        ):
            remove_owned("network", "probe", "owner")
        self.assertEqual(run.call_count, 1)

    def test_cleanup_understands_docker_and_podman_network_labels(self):
        for key in ("Labels", "labels"):
            with self.subTest(key=key), patch("prepare_registry.run") as run:
                run.return_value.stdout = json.dumps([{key: {OWNER_LABEL: "owner"}}])
                remove_owned("network", "probe", "owner")
                self.assertEqual(
                    run.call_args.args, ("docker", "network", "rm", "probe")
                )


if __name__ == "__main__":
    unittest.main()
