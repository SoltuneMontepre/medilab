"""Real Pod/PVC tests. Enable only with MEDILAB_KUBE_TEST_CONFIG pointing to the disposable kind cluster."""

import json
import os
import subprocess
import time
import unittest

from kube_cluster import cleanup_network, inspect, kube, setup_network, validate_cluster, wait_for
from kube_support import Fixture
from runtime import PASSWORD, ROOT


@unittest.skipUnless(os.environ.get("MEDILAB_KUBE_TEST_CONFIG"), "Disposable kind cluster not selected")
class TestKubernetes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        validate_cluster()
        if kube("get", "storageclass", "local-path", check=False).returncode:
            storage = inspect("get", "storageclass", "standard")
            storage["metadata"] = {"name": "local-path"}
            kube("create", "-f", "-", input=json.dumps(storage))
        cls.addClassCleanup(cleanup_network)
        setup_network()

    def fixture(self, **kwargs):
        fixture = Fixture(**kwargs)
        self.addCleanup(fixture.close)
        return fixture

    def test_fresh_healthy_pvc_pod_recreation_and_runtime_recovery(self):
        fixture = self.fixture()
        self.assertFalse(fixture.ready())
        fixture.wait_ready()
        wait_for(lambda: fixture.endpoints() == 1, "Ready Pod was not published.")
        wait_for(lambda: fixture.service_status() == 200, "Ready Service is unavailable.")
        wait_for(lambda: fixture.ingress_status() == 200, "Ready IngressRoute is unavailable.")
        fixture.postgres()
        fixture.scale(0)
        fixture.maintenance(
            'sed \'s/medilab-postgres/retained-postgres/g; s/"MediLab"/"Retained connection"/g\' '
            "workspace/GlobalConfiguration/.dbeaver/data-sources.json > "
            "workspace/GlobalConfiguration/.dbeaver/data-sources-retained.json; "
            "chmod 600 workspace/GlobalConfiguration/.dbeaver/data-sources-retained.json"
        )
        fixture.scale(1)
        fixture.wait_ready()
        pvc = inspect("get", "pvc", "cloudbeaver-workspace", "-n", fixture.namespace)
        identity = pvc["metadata"]["uid"]
        self.assertEqual(pvc["metadata"]["annotations"]["argocd.argoproj.io/sync-options"], "Prune=false,Delete=false")
        kube("annotate", "pvc", "cloudbeaver-workspace", "-n", fixture.namespace, "argocd.argoproj.io/sync-options-")
        original_claim = next(item for item in fixture.resources if item["kind"] == "PersistentVolumeClaim")
        kube("apply", "-f", "-", input=json.dumps(original_claim))
        updated = inspect("get", "pvc", "cloudbeaver-workspace", "-n", fixture.namespace)
        self.assertEqual(updated["metadata"]["uid"], identity)
        self.assertEqual(
            updated["metadata"]["annotations"]["argocd.argoproj.io/sync-options"], "Prune=false,Delete=false"
        )
        summary = subprocess.check_output(
            [
                "python3",
                str(ROOT / "tools/cloudbeaver/preflight.py"),
                "--context",
                "kind-medilab-286-review",
                "--kubeconfig",
                os.environ["MEDILAB_KUBE_TEST_CONFIG"],
                "--namespace",
                fixture.namespace,
            ],
            text=True,
        )
        self.assertNotIn(PASSWORD, summary)
        self.assertNotIn("LocalDatabase9", summary)
        self.assertTrue(json.loads(summary)["workspace"]["workspace_is_mountpoint"])
        with fixture.api() as api:
            self.assertEqual(api.login(), "operator")
            self.assertTrue(
                api.query(
                    'mutation { initConnection(id: "retained-postgres", '
                    'projectId: "g_GlobalConfiguration") { connected } }'
                )["data"]["initConnection"]["connected"]
            )
            api.query('{ createUser(userId: "retained-user", enabled: true) { userId } }')
            inventory = api.query("{ listUsers(page: {}, filter: {}) { userId authRole grantedTeams enabled } }")[
                "data"
            ]
        pod = fixture.pods()[0]
        output = kube(
            "exec",
            "-n",
            fixture.namespace,
            pod["metadata"]["name"],
            "--",
            "/bin/bash",
            "-c",
            "ps -eo uid,comm | awk '$2 == \"java\" {print $1}'; "
            "stat -c '%u:%g:%a' workspace/GlobalConfiguration/.dbeaver/data-sources.json",
        ).stdout
        self.assertIn("8978", output)
        self.assertIn("8978:8978:600", output)
        self.assertIn("workspace is in use", fixture.contender())
        self.assertEqual(fixture.contender_state, "Failed")
        original_pod = fixture.pods()[0]
        restarts = original_pod["status"]["containerStatuses"][0]["restartCount"]
        kube(
            "exec",
            "-n",
            fixture.namespace,
            original_pod["metadata"]["name"],
            "--",
            "/bin/bash",
            "-c",
            "kill -KILL $(pgrep -u 8978 -x java)",
            check=False,
        )
        wait_for(
            lambda: (
                bool(fixture.pods())
                and fixture.pods()[0]["status"].get("containerStatuses", [{}])[0].get("restartCount", 0) > restarts
            ),
            "Application container did not restart after SIGKILL.",
        )
        fixture.wait_ready()
        self.assertEqual(fixture.pods()[0]["metadata"]["uid"], original_pod["metadata"]["uid"])
        for _ in range(2):
            old = fixture.pods()[0]["metadata"]["uid"]
            kube("delete", "pod", fixture.pods()[0]["metadata"]["name"], "-n", fixture.namespace, "--wait=true")
            wait_for(
                lambda previous=old: bool(fixture.pods()) and fixture.pods()[0]["metadata"]["uid"] != previous,
                "Replacement Pod missing.",
            )
            fixture.wait_ready()
            self.assertEqual(
                inspect("get", "pvc", "cloudbeaver-workspace", "-n", fixture.namespace)["metadata"]["uid"], identity
            )
            with fixture.api() as api:
                self.assertEqual(api.login(), "operator")
                self.assertTrue(
                    api.query(
                        'mutation { initConnection(id: "retained-postgres", '
                        'projectId: "g_GlobalConfiguration") { connected } }'
                    )["data"]["initConnection"]["connected"]
                )
                self.assertEqual(
                    api.query("{ listUsers(page: {}, filter: {}) { userId authRole grantedTeams enabled } }")["data"],
                    inventory,
                )
        fixture.scale(0)
        before = fixture.maintenance(
            "sha256sum workspace/.data/cb.h2v2.dat.mv.db; "
            "mv workspace/.data/.cloudbeaver.runtime.conf workspace/.data/review-runtime.saved"
        )
        fixture.scale(1)
        wait_for(
            lambda: bool(fixture.pods()) and bool(fixture.pods()[0].get("status", {}).get("initContainerStatuses")),
            "Init status missing.",
        )
        time.sleep(3)
        self.assertFalse(fixture.ready())
        wait_for(lambda: fixture.endpoints() == 0, "Incomplete workspace has a Ready endpoint.")
        self.assertNotEqual(fixture.service_status(), 200)
        self.assertIn(fixture.ingress_status(), (404, 502, 503))
        fixture.scale(0)
        after = fixture.maintenance(
            "sha256sum workspace/.data/cb.h2v2.dat.mv.db; "
            "mv workspace/.data/review-runtime.saved workspace/.data/.cloudbeaver.runtime.conf"
        )
        self.assertEqual(before, after)
        fixture.scale(1)
        fixture.wait_ready()
        with fixture.api() as api:
            self.assertEqual(api.login(), "operator")

    def test_interrupted_first_start_requires_explicit_recovery_and_then_survives(self):
        fixture = self.fixture(replicas=0)
        fixture.maintenance(
            "test ! -e workspace/.data/cb.h2v2.dat.mv.db; printf interrupted > workspace/.medilab-bootstrap-attempt"
        )
        fixture.scale(1)
        time.sleep(5)
        self.assertFalse(fixture.ready())
        self.assertEqual(fixture.endpoints(), 0)
        self.assertNotEqual(fixture.service_status(), 200)
        self.assertIn(fixture.ingress_status(), (404, 502, 503))
        fixture.scale(0)
        # Deliberate recovery on a disposable, inspected first-time fixture; never part of normal GitOps.
        spec = fixture.deployment["spec"]["template"]["spec"]
        spec["initContainers"][0]["command"] = [
            "/bin/bash",
            "-c",
            'gson=(server/plugins/com.google.gson_*.jar); javac -cp "${gson[0]}" -d /bootstrap-bin /bootstrap/*.java',
        ]
        spec["containers"][0]["command"] = ["/bin/bash", "./launch-product.sh"]
        fixture.scale(1)
        fixture.wait_ready()
        fixture.scale(0)
        fixture.deployment = fixture.normal
        fixture.scale(1)
        fixture.wait_ready()
        with fixture.api() as api:
            self.assertEqual(api.login(), "operator")

    def test_configuration_mode_and_accountless_runtime_never_reach_ingress(self):
        fixture = self.fixture(replicas=0)
        fixture.secret("cloudbeaver-admin", {"CB_ADMIN_NAME": "admin", "CB_ADMIN_PASSWORD": "LocalRegression9"})
        spec = fixture.deployment["spec"]["template"]["spec"]
        spec["initContainers"][0]["command"] = [
            "/bin/bash",
            "-c",
            'gson=(server/plugins/com.google.gson_*.jar); javac -cp "${gson[0]}" -d /bootstrap-bin /bootstrap/*.java',
        ]
        spec["containers"][0]["command"] = ["/bin/bash", "./launch-product.sh"]
        fixture.scale(1)
        wait_for(
            lambda: bool(fixture.pods()) and fixture.pods()[0].get("status", {}).get("phase") == "Running",
            "Collision fixture did not start.",
        )
        with fixture.api() as api:
            api.wait(configuration_mode=True)
        self.assertFalse(fixture.ready())
        self.assertEqual(fixture.endpoints(), 0)
        self.assertNotEqual(fixture.service_status(), 200)
        self.assertIn(fixture.ingress_status(), (404, 502, 503))
        fixture.scale(0)
        fixture.maintenance(
            "test -s workspace/.data/cb.h2v2.dat.mv.db; "
            'printf \'%s\' \'{"server":{"serverName":"Regression"}}\' > workspace/.data/.cloudbeaver.runtime.conf'
        )
        fixture.secret("cloudbeaver-admin", {"CB_ADMIN_NAME": "operator", "CB_ADMIN_PASSWORD": "LocalRegression9"})
        fixture.deployment = fixture.normal
        fixture.scale(1)
        wait_for(
            lambda: bool(fixture.pods()) and fixture.pods()[0].get("status", {}).get("phase") == "Running",
            "Accountless fixture did not start.",
        )
        with fixture.api() as api:
            api.wait()
        time.sleep(4)
        self.assertFalse(fixture.ready())
        self.assertEqual(fixture.endpoints(), 0)
        self.assertIn(fixture.ingress_status(), (404, 502, 503))

    def test_wrong_verifier_is_blocked_then_corrected_without_account_reset(self):
        fixture = self.fixture()
        fixture.wait_ready()
        fixture.scale(0)
        container = fixture.deployment["spec"]["template"]["spec"]["containers"][0]
        verifier = next(value for value in container["env"] if value["name"] == "CB_VERIFY_PASSWORD")
        verifier.pop("valueFrom")
        verifier["value"] = "WrongVerificationPassword9"
        fixture.scale(1)
        wait_for(
            lambda: bool(fixture.pods()) and fixture.pods()[0].get("status", {}).get("phase") == "Running",
            "Verifier fixture did not start.",
        )
        with fixture.api() as api:
            api.wait()
            self.assertEqual(api.login(), "operator")
        time.sleep(4)
        self.assertFalse(fixture.ready())
        self.assertEqual(fixture.endpoints(), 0)
        self.assertIn(fixture.ingress_status(), (404, 502, 503))
        fixture.scale(0)
        fixture.deployment = fixture.normal
        fixture.scale(1)
        fixture.wait_ready()
        with fixture.api() as api:
            self.assertEqual(api.login(), "operator")


if __name__ == "__main__":
    unittest.main()
