import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from kube_support import Fixture

ROOT = Path(__file__).resolve().parents[2]


class TestKubeManifest(unittest.TestCase):
    def test_fixture_sends_only_ingress_route_document_to_kubectl(self):
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": "cloudbeaver"},
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": "cloudbeaver",
                                "startupProbe": {"periodSeconds": 10},
                                "readinessProbe": {"periodSeconds": 10},
                            }
                        ]
                    }
                }
            },
        }
        route = {
            "apiVersion": "traefik.io/v1alpha1",
            "kind": "IngressRoute",
            "metadata": {"name": "cloudbeaver"},
            "spec": {"routes": [{"match": "Host(`cloudbeaver.test`)"}]},
        }

        def fake_kube(*args, **kwargs):
            if args[:2] == ("create", "--dry-run=client"):
                document = kwargs.get("input")
                self.assertIsInstance(document, str)
                self.assertIn("kind: IngressRoute", document)
                self.assertNotIn("kind: Middleware", document)
                return SimpleNamespace(stdout=json.dumps(route))
            return SimpleNamespace(stdout="")

        with (
            patch("kube_support.core_resources", return_value=[deployment]),
            patch("kube_support.kube", side_effect=fake_kube),
            patch("kube_support.ROOT", ROOT),
        ):
            Fixture(replicas=0)
