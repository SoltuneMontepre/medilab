"""CloudBeaver fixtures on the explicitly validated disposable kind cluster."""

import base64
import contextlib
import http.cookiejar
import json
import os
import re
import selectors
import subprocess
import urllib.request
import uuid

from kube_cluster import CONTEXT, NETWORK_NAMESPACE, http_status, inspect, kube, wait_for
from runtime import IMAGE, PASSWORD, ROOT, Runtime


def core_resources():
    rendered = subprocess.check_output(["kubectl", "kustomize", str(ROOT / "infra/cluster/cloudbeaver")], text=True)
    documents = []
    for document in re.split(r"^---\s*$", rendered, flags=re.M):
        match = re.search(r"^kind: (\S+)", document, re.M)
        if match and match[1] in {"ConfigMap", "Deployment", "Service", "PersistentVolumeClaim"}:
            documents.append(document)
    return [
        json.loads(
            kube("create", "--dry-run=client", "--validate=false", "-f", "-", "-o", "json", input=document).stdout
        )
        for document in documents
    ]


class Fixture:
    def __init__(self, replicas=1):
        self.namespace = "medilab-286-" + uuid.uuid4().hex[:10]
        self.resources = core_resources()
        self.deployment = next(item for item in self.resources if item["kind"] == "Deployment")
        for item in self.resources:
            item["metadata"]["namespace"] = self.namespace
        spec = self.deployment["spec"]["template"]["spec"]
        spec["containers"][0]["startupProbe"]["periodSeconds"] = 1
        spec["containers"][0]["readinessProbe"]["periodSeconds"] = 2
        self.normal = json.loads(json.dumps(self.deployment))
        self.deployment["spec"]["replicas"] = replicas
        kube("create", "namespace", self.namespace)
        kube("label", "namespace", self.namespace, "medilab-regression=cloudbeaver")
        self.secret("cloudbeaver-admin", {"CB_ADMIN_NAME": "operator", "CB_ADMIN_PASSWORD": PASSWORD})
        self.secret("medilab-db-app", {"username": "regression", "password": "LocalDatabase9"})
        kube("apply", "-f", "-", input=json.dumps({"apiVersion": "v1", "kind": "List", "items": self.resources}))
        route = json.loads(
            kube(
                "create",
                "--dry-run=client",
                "--validate=false",
                "-f",
                str(ROOT / "infra/cluster/cloudbeaver/ingress-route.yaml"),
                "-o",
                "json",
            ).stdout
        )
        route["metadata"]["namespace"] = self.namespace
        route["spec"]["routes"][0]["match"] = f"Host(`{self.namespace}.test`)"
        kube("apply", "-f", "-", input=json.dumps(route))

    def secret(self, name, values):
        value = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": name, "namespace": self.namespace},
            "data": {key: base64.b64encode(value.encode()).decode() for key, value in values.items()},
        }
        kube("apply", "-f", "-", input=json.dumps(value))

    def apply(self):
        kube("apply", "-f", "-", input=json.dumps(self.deployment))

    def pods(self):
        return inspect("get", "pods", "-n", self.namespace, "-l", "app.kubernetes.io/name=cloudbeaver")["items"]

    def ready(self):
        pods = self.pods()
        return len(pods) == 1 and any(
            condition["type"] == "Ready" and condition["status"] == "True"
            for condition in pods[0].get("status", {}).get("conditions", [])
        )

    def wait_ready(self):
        wait_for(self.ready, "CloudBeaver Pod did not become Ready.")

    def wait_guard_rejected(self, reason):
        def rejected():
            for pod in self.pods():
                for status in pod.get("status", {}).get("initContainerStatuses", []):
                    failed = any(
                        state.get("terminated", {}).get("exitCode", 0) != 0
                        for state in (status.get("state", {}), status.get("lastState", {}))
                    )
                    if failed:
                        logs = kube(
                            "logs", "-n", self.namespace, pod["metadata"]["name"], "-c", status["name"], check=False
                        ).stdout
                        if "CloudBeaver startup blocked." in logs and reason in logs:
                            return True
            return False

        wait_for(rejected, "Workspace preparation did not report the expected guard rejection.")

    def wait_readiness_rejected(self):
        def rejected():
            for pod in self.pods():
                events = inspect(
                    "get",
                    "events",
                    "-n",
                    self.namespace,
                    "--field-selector",
                    "involvedObject.uid=" + pod["metadata"]["uid"] + ",reason=Unhealthy",
                )["items"]
                if any("Readiness probe failed" in event.get("message", "") for event in events):
                    return True
            return False

        wait_for(rejected, "Kubelet did not report an actual readiness probe rejection.")

    def consumer(self, name, read_only):
        pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": name, "namespace": self.namespace},
            "spec": {
                "restartPolicy": "Never",
                "terminationGracePeriodSeconds": 1,
                "containers": [
                    {
                        "name": "inspector",
                        "image": IMAGE,
                        "command": ["sleep", "600"],
                        "volumeMounts": [{"name": "workspace", "mountPath": "/workspace", "readOnly": read_only}],
                    }
                ],
                "volumes": [{"name": "workspace", "persistentVolumeClaim": {"claimName": "cloudbeaver-workspace"}}],
            },
        }
        kube("create", "-f", "-", input=json.dumps(pod))
        wait_for(
            lambda: inspect("get", "pod", name, "-n", self.namespace).get("status", {}).get("phase") == "Running",
            "Same-claim inspection fixture did not start.",
        )

    def endpoints(self):
        slices = inspect("get", "endpointslices", "-n", self.namespace, "-l", "kubernetes.io/service-name=cloudbeaver")[
            "items"
        ]
        return sum(
            endpoint.get("conditions", {}).get("ready") is True
            for item in slices
            for endpoint in item.get("endpoints", [])
        )

    def service_status(self):
        return http_status(f"http://cloudbeaver.{self.namespace}.svc.cluster.local:8978/")

    def ingress_status(self):
        return http_status(f"http://traefik.{NETWORK_NAMESPACE}.svc.cluster.local/", f"{self.namespace}.test")

    def postgres(self):
        pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": "postgres", "namespace": self.namespace, "labels": {"app": "regression-postgres"}},
            "spec": {
                "containers": [
                    {
                        "name": "postgres",
                        "image": "docker.io/library/postgres:18.4",
                        "env": [
                            {"name": "POSTGRES_USER", "value": "regression"},
                            {"name": "POSTGRES_PASSWORD", "value": "LocalDatabase9"},
                            {"name": "POSTGRES_DB", "value": "medilab"},
                        ],
                        "readinessProbe": {
                            "exec": {"command": ["pg_isready", "-h", "127.0.0.1", "-U", "regression", "-d", "medilab"]},
                            "periodSeconds": 1,
                        },
                    }
                ]
            },
        }
        service = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {"name": "medilab-db-rw", "namespace": self.namespace},
            "spec": {"selector": {"app": "regression-postgres"}, "ports": [{"port": 5432}]},
        }
        kube("apply", "-f", "-", input=json.dumps({"apiVersion": "v1", "kind": "List", "items": [pod, service]}))
        wait_for(
            lambda: any(
                condition["type"] == "Ready" and condition["status"] == "True"
                for condition in inspect("get", "pod", "postgres", "-n", self.namespace)
                .get("status", {})
                .get("conditions", [])
            ),
            "Synthetic PostgreSQL did not become ready.",
        )

    def contender(self):
        spec = self.deployment["spec"]["template"]["spec"]
        pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": "contender", "namespace": self.namespace},
            "spec": {"restartPolicy": "Never", "containers": [spec["initContainers"][0]], "volumes": spec["volumes"]},
        }
        kube("create", "-f", "-", input=json.dumps(pod))
        wait_for(
            lambda: (
                inspect("get", "pod", "contender", "-n", self.namespace).get("status", {}).get("phase")
                in {"Failed", "Succeeded"}
            ),
            "Concurrent preparation did not terminate.",
        )
        self.contender_state = inspect("get", "pod", "contender", "-n", self.namespace)["status"]["phase"]
        return kube("logs", "contender", "-n", self.namespace).stdout

    def scale(self, replicas):
        self.deployment["spec"]["replicas"] = replicas
        self.apply()
        if replicas == 0:
            wait_for(lambda: not self.pods(), "CloudBeaver writer did not terminate.")

    def maintenance(self, command):
        if self.pods():
            raise AssertionError("Fixture maintenance requires the application stopped.")
        name = "maintenance-" + uuid.uuid4().hex[:8]
        pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": name, "namespace": self.namespace},
            "spec": {
                "restartPolicy": "Never",
                "containers": [
                    {
                        "name": "maintenance",
                        "image": IMAGE,
                        "command": ["/bin/bash", "-c", "set -euo pipefail; " + command],
                        "volumeMounts": [{"name": "workspace", "mountPath": "/opt/cloudbeaver/workspace"}],
                    }
                ],
                "volumes": [{"name": "workspace", "persistentVolumeClaim": {"claimName": "cloudbeaver-workspace"}}],
            },
        }
        kube("create", "-f", "-", input=json.dumps(pod))
        wait_for(
            lambda: (
                inspect("get", "pod", name, "-n", self.namespace).get("status", {}).get("phase")
                in {"Succeeded", "Failed"}
            ),
            "Fixture maintenance did not complete.",
        )
        state = inspect("get", "pod", name, "-n", self.namespace)
        result = kube("logs", name, "-n", self.namespace).stdout
        kube("delete", "pod", name, "-n", self.namespace, "--wait=true")
        if state["status"]["phase"] != "Succeeded":
            raise AssertionError("Fixture maintenance failed; output omitted.")
        return result

    @contextlib.contextmanager
    def api(self):
        wait_for(
            lambda: any(
                status.get("name") == "cloudbeaver" and status.get("started") is True
                for pod in self.pods()
                for status in pod.get("status", {}).get("containerStatuses", [])
            ),
            "Application listener did not pass its startup probe.",
        )
        process = subprocess.Popen(
            [
                "kubectl",
                "--kubeconfig",
                os.environ["MEDILAB_KUBE_TEST_CONFIG"],
                "--context",
                CONTEXT,
                "port-forward",
                "-n",
                self.namespace,
                "deployment/cloudbeaver",
                ":8978",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            if not selector.select(15):
                raise AssertionError("Disposable-cluster port-forward did not start.")
            line = process.stdout.readline()
            match = re.search(r"127\.0\.0\.1:(\d+)", line)
            if not match:
                raise AssertionError("Unexpected port-forward state.")
            api = Runtime.__new__(Runtime)
            api.port = int(match[1])
            api.env = {"CB_ADMIN_PASSWORD": PASSWORD, "DB_PASSWORD": "LocalDatabase9"}
            api.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            yield api
        finally:
            selector.close()
            process.terminate()
            process.wait(timeout=10)
            process.stdout.close()

    def close(self):
        kube("delete", "namespace", self.namespace, "--wait=false", check=False)
