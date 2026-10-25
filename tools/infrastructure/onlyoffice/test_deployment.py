"""Security/configuration contracts; real CNI, browser and retention acceptance remain separate."""

import base64
import hashlib
import hmac
import json
import subprocess
import unittest
from pathlib import Path

import recover
import yaml

ROOT = Path(__file__).resolve().parents[3]
IMAGE = "docker.io/onlyoffice/documentserver:9.4.0.1@sha256:3ab6ebc7c605e5a32b7ae3ff19daed4925090245acc8100ce2230bd766c88212"


def render(path):
    result = subprocess.run(["kubectl", "kustomize", str(ROOT / path)], check=True, capture_output=True, text=True)
    return list(yaml.safe_load_all(result.stdout))


def named(resources, kind, name):
    return next(r for r in resources if r["kind"] == kind and r["metadata"]["name"] == name)


def matches(selector, labels):
    return all(labels.get(key) == value for key, value in selector.get("matchLabels", {}).items())


class TestDeployment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = render("infra/cluster/onlyoffice")
        cls.odoo = render("infra/cluster/onlyoffice-integration")
        cls.edge = render("infra/cluster/onlyoffice-edge")
        cls.monitor = render("infra/cluster/onlyoffice-monitor")
        cls.policy = named(cls.server, "NetworkPolicy", "onlyoffice-isolation")["spec"]

    def permits(self, destination, namespace, port):
        for rule in self.policy["egress"]:
            if port not in [p["port"] for p in rule["ports"]]:
                continue
            for peer in rule["to"]:
                if matches(peer.get("podSelector", {}), destination) and matches(
                    peer.get("namespaceSelector", {}), {"kubernetes.io/metadata.name": namespace}
                ):
                    return True
        return False

    def test_routing_allows_only_selected_callback_and_dns(self):
        self.assertTrue(self.permits({"app.kubernetes.io/name": "traefik"}, "kube-system", 8443))
        self.assertTrue(self.permits({"k8s-app": "kube-dns"}, "kube-system", 53))
        for labels, namespace, port in [
            ({"app.kubernetes.io/name": "odoo"}, "medilab", 8069),
            ({"app.kubernetes.io/name": "traefik"}, "kube-system", 80),
            ({"app.kubernetes.io/name": "traefik"}, "medilab", 8443),
            ({}, "metadata", 80),
            ({}, "internet", 443),
            ({"app.kubernetes.io/name": "postgres"}, "medilab", 5432),
        ]:
            with self.subTest(labels=labels, namespace=namespace, port=port):
                self.assertFalse(self.permits(labels, namespace, port))

    def test_no_wildcard_or_private_range_egress(self):
        for rule in self.policy["egress"]:
            self.assertTrue(rule["to"])
            for peer in rule["to"]:
                self.assertIn("podSelector", peer)
                self.assertIn("namespaceSelector", peer)
                self.assertTrue(peer["podSelector"]["matchLabels"])

    def test_callback_does_not_bypass_traefik_or_use_cloudflare(self):
        ingress = named(self.odoo, "IngressRoute", "onlyoffice-callback")["spec"]
        self.assertEqual(ingress["entryPoints"], ["onlyofficecallback"])
        route = ingress["routes"][0]
        self.assertIn("PathPrefix(`/medilab/laboratory-files/callback/`)", route["match"])
        self.assertIn("Method(`POST`)", route["match"])
        base = named(render("infra/cluster/odoo"), "NetworkPolicy", "odoo-from-traefik")
        self.assertEqual(base, named(self.odoo, "NetworkPolicy", "odoo-from-traefik"))
        public = named(self.odoo, "IngressRoute", "odoo")["spec"]["routes"][-1]
        self.assertIn("!PathPrefix(`/medilab/laboratory-files/callback/`)", public["match"])

    def test_readiness_independent_of_document_server(self):
        base = named(render("infra/cluster/odoo"), "Deployment", "odoo")["spec"]["template"]["spec"]
        derived = named(self.odoo, "Deployment", "odoo")["spec"]["template"]["spec"]
        self.assertEqual(derived["initContainers"][0]["image"], derived["containers"][0]["image"])
        for key in ["readinessProbe", "livenessProbe", "startupProbe"]:
            self.assertEqual(base["containers"][0][key], derived["containers"][0][key])
        monitor = named(self.monitor, "Deployment", "onlyoffice-monitor")["spec"]["template"]["spec"]
        self.assertFalse(monitor["automountServiceAccountToken"])
        self.assertNotIn("odoo", json.dumps(monitor))

    def test_image_state_and_claim_protection(self):
        spec = named(self.server, "Deployment", "onlyoffice")["spec"]
        self.assertEqual(spec["strategy"]["type"], "Recreate")
        self.assertEqual(spec["replicas"], 1)
        pod = spec["template"]["spec"]
        self.assertEqual(pod["hostname"], "onlyoffice")
        self.assertFalse(pod["automountServiceAccountToken"])
        container = pod["containers"][0]
        self.assertEqual(container["image"], IMAGE)
        paths = {m["mountPath"] for m in container["volumeMounts"] if m["name"] == "state"}
        self.assertEqual(
            paths,
            {
                "/var/lib/onlyoffice",
                "/var/www/onlyoffice/Data",
                "/var/lib/postgresql",
                "/var/lib/rabbitmq",
                "/var/lib/redis",
                "/usr/share/fonts/truetype/custom",
            },
        )
        pvc = named(self.server, "PersistentVolumeClaim", "onlyoffice-state")
        self.assertIn("Prune=false,Delete=false", str(pvc["metadata"]["annotations"]))

    def test_jwt_references_and_protocol(self):
        secret = named(self.server, "ExternalSecret", "onlyoffice-jwt")["spec"]
        self.assertEqual(secret["secretStoreRef"], {"kind": "ClusterSecretStore", "name": "doppler"})
        self.assertEqual(secret["data"], [{"secretKey": "jwt-secret", "remoteRef": {"key": "ONLYOFFICE_JWT_SECRET"}}])
        references = []
        for resources, name in [(self.server, "onlyoffice"), (self.odoo, "odoo")]:
            container = named(resources, "Deployment", name)["spec"]["template"]["spec"]["containers"][0]
            references += [
                e["valueFrom"]["secretKeyRef"]
                for e in container["env"]
                if e["name"] in ("JWT_SECRET", "ONLYOFFICE_JWT_SECRET")
            ]
        self.assertEqual(references, [{"name": "onlyoffice-jwt", "key": "jwt-secret"}] * 2)
        settings = json.loads((ROOT / "tools/infrastructure/onlyoffice/settings.json").read_text())["services"][
            "CoAuthoring"
        ]
        self.assertTrue(settings["token"]["enable"]["browser"])
        self.assertEqual(settings["token"]["outbox"]["expires"], "5m")
        self.assertEqual(settings["token"]["outbox"]["urlExclusionRegex"], "")
        self.assertEqual(settings["callbackBackoffOptions"]["retries"], 3)
        self.assertEqual(
            settings["server"]["callbackRequestTimeout"], {"connectionAndInactivity": "21m", "wholeCycle": "21m"}
        )

    def test_trust_without_ca_private_key_or_insecure_override(self):
        pod = named(self.server, "Deployment", "onlyoffice")["spec"]["template"]["spec"]
        self.assertFalse(any(v.get("secret", {}).get("secretName") == "onlyoffice-ca" for v in pod["volumes"]))
        transport = named(self.server, "ServersTransport", "onlyoffice-tls")["spec"]
        self.assertEqual(transport["rootCAsSecrets"], ["onlyoffice-tls"])
        self.assertNotIn("insecureSkipVerify", transport)
        settings = json.loads((ROOT / "tools/infrastructure/onlyoffice/settings.json").read_text())
        self.assertTrue(settings["services"]["CoAuthoring"]["requestDefaults"]["rejectUnauthorized"])
        self.assertFalse(settings["services"]["CoAuthoring"]["request-filtering-agent"]["allowMetaIPAddress"])

    def test_local_parity_and_no_shared_container_name(self):
        compose = yaml.safe_load((ROOT / "src/applications/medilab-sync/docker-compose.yml").read_text())
        service = compose["services"]["onlyoffice"]
        self.assertEqual(service["image"], IMAGE)
        self.assertNotIn("container_name", service)
        self.assertTrue(compose["networks"]["onlyoffice"]["internal"])
        self.assertTrue(service["ports"][0].startswith("127.0.0.1:"))
        for name in ["start.sh", "settings.json"]:
            self.assertEqual(
                (ROOT / "tools/infrastructure/onlyoffice" / name).read_bytes(),
                (ROOT / "infra/cluster/onlyoffice" / name).read_bytes(),
            )
        self.assertEqual(
            (ROOT / "tools/infrastructure/onlyoffice/probe.py").read_bytes(),
            (ROOT / "infra/cluster/onlyoffice-monitor/probe.py").read_bytes(),
        )

    def test_no_automatic_activation(self):
        root = yaml.safe_load((ROOT / "infra/cluster/kustomization.yaml").read_text())
        for name in ["onlyoffice", "onlyoffice-monitor"]:
            self.assertNotIn(f"applications/{name}.yaml", root["resources"])
            application = yaml.safe_load((ROOT / f"infra/cluster/applications/{name}.yaml").read_text())
            self.assertNotIn("automated", application["spec"]["syncPolicy"])
            self.assertTrue((ROOT / application["spec"]["source"]["path"]).is_dir())

    def test_private_routes_have_no_trace_or_access_logs(self):
        for resources, name in [(self.server, "onlyoffice"), (self.odoo, "onlyoffice-callback")]:
            route = named(resources, "IngressRoute", name)["spec"]["routes"][0]
            self.assertEqual(route["observability"], {"accessLogs": False, "tracing": False})
        script = (ROOT / "tools/infrastructure/onlyoffice/start.sh").read_text()
        for setting in ["DS_LOG_LEVEL=OFF", "NGINX_ACCESS_LOG=false", "error_log /dev/null crit", ">/dev/null 2>&1"]:
            self.assertIn(setting, script)

    def test_recovery_only_uses_matching_https_origin(self):
        origin = "https://onlyoffice.medilab.svc.cluster.local"
        self.assertTrue(recover.same_origin(origin + "/cache/output.docx?token=sentinel", origin))
        for url in [
            "http://onlyoffice.medilab.svc.cluster.local/a",
            "https://metadata/a",
            origin + ":8443/a",
            "https://user@onlyoffice.medilab.svc.cluster.local/a",
            origin + "/a#fragment",
            origin + "/a\\b",
            origin + "/a%0a\n",
        ]:
            self.assertFalse(recover.same_origin(url, origin), url)

    def test_operator_command_is_fresh_hs256_and_payload_bound(self):
        body, secret = (
            {"c": "getForgotten", "key": "original-key"},
            b"unit-test-secret-longer-than-thirty-two-characters",
        )
        signed = recover.token(body, secret).split(".")

        def decode(value):
            return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

        self.assertEqual(json.loads(decode(signed[0]))["alg"], "HS256")
        claims = json.loads(decode(signed[1]))
        self.assertEqual(claims["payload"], body)
        self.assertEqual(claims["exp"] - claims["iat"], 300)
        self.assertEqual(decode(signed[2]), hmac.digest(secret, ".".join(signed[:2]).encode(), hashlib.sha256))


if __name__ == "__main__":
    unittest.main()
