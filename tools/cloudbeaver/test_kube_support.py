"""Check guard evidence when kubelet has restarted an init container."""

import unittest
from unittest.mock import Mock, patch

from kube_support import Fixture


class TestGuardEvidence(unittest.TestCase):
    def test_previous_instance_log_preserves_guard_rejection(self):
        fixture = Fixture.__new__(Fixture)
        fixture.namespace = "synthetic-namespace"
        fixture.pods = lambda: [
            {
                "metadata": {"name": "synthetic-pod"},
                "status": {
                    "initContainerStatuses": [
                        {
                            "name": "prepare-workspace",
                            "state": {"running": {}},
                            "lastState": {"terminated": {"exitCode": 1}},
                        }
                    ]
                },
            }
        ]

        def logs(*args, **kwargs):
            self.assertFalse(kwargs["check"])
            if "--previous" in args:
                return Mock(stdout="CloudBeaver startup blocked. Interrupted bootstrap")
            return Mock(stdout="Compiling bootstrap helpers")

        with (
            patch("kube_support.kube", side_effect=logs) as command,
            patch("kube_support.wait_for", side_effect=lambda predicate, _: self.assertTrue(predicate())),
        ):
            fixture.wait_guard_rejected("Interrupted bootstrap")
        self.assertEqual(command.call_count, 2)
        self.assertIn("--previous", command.call_args.args)


if __name__ == "__main__":
    unittest.main()
