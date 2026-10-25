"""Security/configuration contracts; real CNI, browser and retention acceptance remain separate."""

import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import tempfile
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

    def test_worker_sets_config_after_launcher_and_preserves_arguments(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            config = directory / "settings.json"
            binary = directory / "docservice"
            bootstrap = directory / "worker-bootstrap.cjs"
            script = directory / "worker.sh"
            expected = {"services": {"CoAuthoring": {"expire": {"files": 604800}}}}
            config.write_text(json.dumps(expected), encoding="utf-8")
            binary.write_text(
                "#!" + sys.executable + "\nimport json,os,sys\n"
                "print(json.dumps({"
                '"config":json.loads(os.environ["NODE_CONFIG"]),'
                '"pkg":os.environ["PKG_EXECPATH"],"args":sys.argv[1:]}))\n',
                encoding="utf-8",
            )
            binary.chmod(0o700)
            source = (ROOT / "infra/cluster/onlyoffice/worker.sh").read_text()
            source = source.replace("/opt/medilab/onlyoffice/settings.json", str(config))
            source = source.replace("/var/www/onlyoffice/documentserver/server/DocService/docservice", str(binary))
            source = source.replace("/opt/medilab/onlyoffice/worker-bootstrap.cjs", str(bootstrap))
            script.write_text(source, encoding="utf-8")
            arguments = ["argument with spaces", "literal $(not-a-command)"]
            result = subprocess.run(
                ["bash", str(script), str(config), str(binary), *arguments],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
                env=dict(os.environ, NODE_CONFIG='{"stale":true}'),
            )
            self.assertEqual(
                json.loads(result.stdout),
                {"config": expected, "pkg": str(binary), "args": [str(bootstrap), *arguments]},
            )
            self.assertEqual(result.stderr, "")
        start = (ROOT / "infra/cluster/onlyoffice/start.sh").read_text()
        self.assertNotIn("export NODE_CONFIG=", start)
        self.assertIn("for service in docservice converter", start)
        self.assertIn('grep -Fxq "$worker_command" "$supervisor_file"', start)

    def test_worker_refuses_missing_or_empty_config(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "settings.json"
            for create in [False, True]:
                if create:
                    config.touch()
                result = subprocess.run(
                    [
                        "bash",
                        str(ROOT / "infra/cluster/onlyoffice/worker.sh"),
                        str(config),
                        sys.executable,
                        "-c",
                        'print("worker started")',
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout + result.stderr, "")

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
        settings = json.loads((ROOT / "infra/cluster/onlyoffice/settings.json").read_text())["services"]["CoAuthoring"]
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
        settings = json.loads((ROOT / "infra/cluster/onlyoffice/settings.json").read_text())
        self.assertTrue(settings["services"]["CoAuthoring"]["requestDefaults"]["rejectUnauthorized"])
        self.assertFalse(settings["services"]["CoAuthoring"]["request-filtering-agent"]["allowMetaIPAddress"])

    def test_local_parity_and_no_shared_container_name(self):
        compose = yaml.safe_load((ROOT / "src/applications/medilab-sync/docker-compose.yml").read_text())
        service = compose["services"]["onlyoffice"]
        self.assertEqual(service["image"], IMAGE)
        self.assertNotIn("container_name", service)
        self.assertTrue(compose["networks"]["onlyoffice"]["internal"])
        self.assertTrue(service["ports"][0].startswith("127.0.0.1:"))
        mount = next(value for value in service["volumes"] if ":/opt/medilab/onlyoffice:ro" in value)
        mounted = (ROOT / "tools/infrastructure" / mount.split(":", 1)[0]).resolve()
        self.assertEqual(mounted, ROOT / "infra/cluster/onlyoffice")
        config_map = next(resource for resource in self.server if resource["kind"] == "ConfigMap")
        for name, content in config_map["data"].items():
            self.assertEqual((mounted / name).read_text(), content)

    def test_drain_budget_and_probe_wiring(self):
        deployment = named(self.server, "Deployment", "onlyoffice")["spec"]
        pod = deployment["template"]["spec"]
        container = pod["containers"][0]
        self.assertGreaterEqual(pod["terminationGracePeriodSeconds"], 30 + 1.5 * (300 + 900) + 60)
        self.assertGreaterEqual(deployment["progressDeadlineSeconds"], pod["terminationGracePeriodSeconds"] + 600)
        command = ["/bin/bash", "/opt/medilab/onlyoffice/healthcheck.sh"]
        for name in ["startupProbe", "readinessProbe"]:
            self.assertEqual(container[name]["exec"]["command"], command)
            self.assertGreaterEqual(container[name]["timeoutSeconds"], 8)
        # Storage failure must refuse editing without automatically killing in-memory editing state.
        self.assertEqual(container["livenessProbe"]["tcpSocket"], {"port": "https"})
        compose = yaml.safe_load((ROOT / "src/applications/medilab-sync/docker-compose.yml").read_text())
        local = compose["services"]["onlyoffice"]
        self.assertEqual(local["stop_grace_period"], str(pod["terminationGracePeriodSeconds"]) + "s")
        self.assertEqual(local["healthcheck"]["test"], ["CMD", *command])

    def test_runtime_drops_raw_sockets_and_keeps_secret_file_private(self):
        pod = named(self.server, "Deployment", "onlyoffice")["spec"]["template"]["spec"]
        for container in [*pod["containers"], *pod["initContainers"]]:
            self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
            self.assertIn("NET_RAW", container["securityContext"]["capabilities"]["drop"])
        script = (ROOT / "infra/cluster/onlyoffice/start.sh").read_text()
        self.assertIn("chmod 0600 /etc/onlyoffice/documentserver/local.json", script)
        self.assertIn('sudo -u ds test -r "$NODE_EXTRA_CA_CERTS"', script)
        self.assertIn("private_dir=/var/www/onlyoffice/Data/.private", script)
        self.assertIn('secure_link_file="$private_dir/medilab-secure-link-secret"', script)
        self.assertIn('export SECURE_LINK_SECRET="$(cat "$secure_link_file")"', script)

    def test_health_body_and_required_process_failures_are_private(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            for name, source in {
                "supervisorctl": '#!/bin/sh\nexit "${MOCK_PROCESS_EXIT:-0}"\n',
                "curl": '#!/bin/sh\nprintf "%s" "$MOCK_HEALTH_BODY"\nexit "${MOCK_CURL_EXIT:-0}"\n',
                "sudo": '#!/bin/sh\nexit "${MOCK_POLICY_EXIT:-0}"\n',
            }.items():
                path = directory / name
                path.write_text(source, encoding="utf-8")
                path.chmod(0o700)
            cases = [
                ("true", "0", "0", "0", 0),
                ("false", "0", "0", "0", 1),
                ("", "0", "0", "0", 1),
                ("true extra", "0", "0", "0", 1),
                ("true", "3", "0", "0", 1),
                ("true", "0", "60", "0", 1),
                ("true", "0", "0", "1", 1),
            ]
            for body, process_exit, curl_exit, policy_exit, expected in cases:
                with self.subTest(body=body, process_exit=process_exit, curl_exit=curl_exit):
                    env = dict(
                        os.environ,
                        PATH=str(directory) + os.pathsep + os.environ["PATH"],
                        MOCK_HEALTH_BODY=body,
                        MOCK_PROCESS_EXIT=process_exit,
                        MOCK_CURL_EXIT=curl_exit,
                        MOCK_POLICY_EXIT=policy_exit,
                    )
                    result = subprocess.run(
                        ["bash", str(ROOT / "infra/cluster/onlyoffice/healthcheck.sh")],
                        env=env,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode == 0, expected == 0)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(result.stderr, "")

    def test_shutdown_requires_successful_transport_and_true_drain(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            curl = directory / "curl"
            curl.write_text('#!/bin/sh\nprintf "%s" "$MOCK_BODY"\nexit "$MOCK_CURL_EXIT"\n', encoding="utf-8")
            curl.chmod(0o700)
            for body, curl_exit, expected in [("true", "0", 0), ("false", "0", 1), ("true", "28", 1)]:
                with self.subTest(body=body, curl_exit=curl_exit):
                    env = dict(
                        os.environ,
                        PATH=str(directory) + os.pathsep + os.environ["PATH"],
                        MOCK_BODY=body,
                        MOCK_CURL_EXIT=curl_exit,
                    )
                    result = subprocess.run(
                        ["bash", str(ROOT / "infra/cluster/onlyoffice/shutdown.sh")],
                        env=env,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode == 0, expected == 0)
                    self.assertEqual(result.stdout + result.stderr, "")
        script = (ROOT / "infra/cluster/onlyoffice/shutdown.sh").read_text()
        self.assertIn("--max-time 1860", script)
        self.assertIn("--noproxy '*'", script)

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
        script = (ROOT / "infra/cluster/onlyoffice/start.sh").read_text()
        for setting in ["DS_LOG_LEVEL=OFF", "NGINX_ACCESS_LOG=false", "error_log /dev/null crit", ">/dev/null 2>&1"]:
            self.assertIn(setting, script)

    def test_public_route_excludes_command_aliases(self):
        route = named(self.server, "IngressRoute", "onlyoffice")["spec"]["routes"][0]
        pattern = route["match"].split("!PathRegexp(`", 1)[1].split("`)", 1)[0]
        for path in [
            "/command",
            "/COMMAND",
            "/coauthoring/CommandService.ashx",
            "/9.4.0-129/command",
            "/9.4.0-129/coauthoring/CommandService.ashx",
        ]:
            self.assertIsNotNone(re.search(pattern, path), path)
        for path in ["/healthcheck", "/web-apps/apps/api/documents/api.js", "/9.4.0-129/doc/session/c"]:
            self.assertIsNone(re.search(pattern, path), path)

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
