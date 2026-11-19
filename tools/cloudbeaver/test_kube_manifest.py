import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from kube_support import Fixture

ROOT = Path(__file__).resolve().parents[2]


class TestKubeManifest(unittest.TestCase):
    def test_fixture_applies_each_route_dependency_from_multidocument_manifest(self):
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
        resources = {
            "Middleware": {
                "apiVersion": "traefik.io/v1alpha1",
                "kind": "Middleware",
                "metadata": {"name": "cloudbeaver-host"},
                "spec": {
                    "headers": {
                        "customRequestHeaders": {
                            "X-Forwarded-Host": "cloudbeaver.soltunemontepre.tech"
                        }
                    }
                },
            },
            "IngressRoute": {
                "apiVersion": "traefik.io/v1alpha1",
                "kind": "IngressRoute",
                "metadata": {"name": "cloudbeaver"},
                "spec": {
                    "routes": [
                        {
                            "kind": "Rule",
                            "match": "Host(`cloudbeaver.soltunemontepre.tech`)",
                            "middlewares": [{"name": "cloudbeaver-host"}],
                            "services": [{"name": "cloudbeaver", "port": "http"}],
                        }
                    ]
                },
            },
        }
        created_kinds = []
        applied_resources = []

        def fake_kube(*args, **kwargs):
            if args[:2] == ("create", "--dry-run=client"):
                document = kwargs.get("input")
                self.assertIsInstance(document, str)
                kinds = [
                    line.removeprefix("kind: ")
                    for line in document.splitlines()
                    if line.startswith("kind: ")
                ]
                self.assertEqual(len(kinds), 1)
                kind = kinds[0]
                self.assertIn(kind, resources)
                created_kinds.append(kind)
                return SimpleNamespace(stdout=json.dumps(resources[kind]))
            if args and args[0] == "apply":
                value = json.loads(kwargs.get("input", "{}"))
                if value.get("kind") in resources:
                    applied_resources.append(value)
            return SimpleNamespace(stdout="")

        with (
            patch("kube_support.core_resources", return_value=[deployment]),
            patch("kube_support.kube", side_effect=fake_kube),
            patch("kube_support.ROOT", ROOT),
        ):
            fixture = Fixture(replicas=0)

        self.assertEqual(created_kinds, ["Middleware", "IngressRoute"])
        self.assertEqual(
            [resource["kind"] for resource in applied_resources],
            ["Middleware", "IngressRoute"],
        )
        self.assertEqual(
            [resource["metadata"]["namespace"] for resource in applied_resources],
            [fixture.namespace, fixture.namespace],
        )
        self.assertEqual(
            applied_resources[1]["spec"]["routes"][0]["match"],
            f"Host(`{fixture.namespace}.test`)",
        )
