"""Helpers restricted to the disposable kind cluster used for CloudBeaver regressions."""

import json
import os
import subprocess
import time
import urllib.request

CONTEXT = "kind-medilab-286-review"
NETWORK_NAMESPACE = "medilab-286-network"


def kube(*args, input=None, check=True):
    result = subprocess.run(
        ["kubectl", "--kubeconfig", os.environ["MEDILAB_KUBE_TEST_CONFIG"], "--context", CONTEXT, *args],
        input=input,
        text=True,
        capture_output=True,
        timeout=150,
        check=False,
    )
    if check and result.returncode:
        raise AssertionError(f"Disposable-cluster {args[0]} failed (exit {result.returncode}); response omitted.")
    return result


def inspect(*args):
    return json.loads(kube(*args, "-o", "json").stdout)


def wait_for(predicate, message, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(1)
    raise AssertionError(message)


def validate_cluster():
    config = inspect("config", "view", "--minify")
    if not config["clusters"][0]["cluster"]["server"].startswith("https://127.0.0.1:"):
        raise AssertionError("Only the disposable loopback kind cluster is allowed.")
    nodes = inspect("get", "nodes")["items"]
    if len(nodes) != 1 or nodes[0]["metadata"]["name"] != "medilab-286-review-control-plane":
        raise AssertionError("Unexpected cluster; no resources may be changed.")


def setup_network():
    kube("create", "namespace", NETWORK_NAMESPACE)
    with urllib.request.urlopen(
        "https://raw.githubusercontent.com/traefik/traefik/v3.7.13/docs/content/reference/dynamic-configuration/kubernetes-crd-definition-v1.yml",
        timeout=20,
    ) as response:
        kube("apply", "--server-side", "-f", "-", input=response.read().decode())
    service_account = {
        "apiVersion": "v1",
        "kind": "ServiceAccount",
        "metadata": {"name": "traefik", "namespace": NETWORK_NAMESPACE},
    }
    role = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRole",
        "metadata": {"name": "medilab-286-traefik"},
        "rules": [
            {
                "apiGroups": [""],
                "resources": ["services", "secrets", "configmaps", "nodes", "endpoints"],
                "verbs": ["get", "list", "watch"],
            },
            {"apiGroups": ["discovery.k8s.io"], "resources": ["endpointslices"], "verbs": ["get", "list", "watch"]},
            {"apiGroups": ["networking.k8s.io"], "resources": ["ingressclasses"], "verbs": ["get", "list", "watch"]},
            {"apiGroups": ["traefik.io"], "resources": ["*"], "verbs": ["get", "list", "watch"]},
        ],
    }
    binding = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRoleBinding",
        "metadata": {"name": "medilab-286-traefik"},
        "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "ClusterRole", "name": "medilab-286-traefik"},
        "subjects": [{"kind": "ServiceAccount", "name": "traefik", "namespace": NETWORK_NAMESPACE}],
    }
    deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "traefik", "namespace": NETWORK_NAMESPACE},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app": "traefik"}},
            "template": {
                "metadata": {"labels": {"app": "traefik"}},
                "spec": {
                    "serviceAccountName": "traefik",
                    "containers": [
                        {
                            "name": "traefik",
                            "image": "docker.io/library/traefik:v3.7.13",
                            "args": [
                                "--entrypoints.web.address=:8000",
                                "--providers.kubernetescrd=true",
                                "--ping=true",
                                "--ping.entrypoint=web",
                            ],
                            "ports": [{"containerPort": 8000}],
                            "readinessProbe": {"httpGet": {"path": "/ping", "port": 8000}},
                        }
                    ],
                },
            },
        },
    }
    service = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": "traefik", "namespace": NETWORK_NAMESPACE},
        "spec": {"selector": {"app": "traefik"}, "ports": [{"port": 80, "targetPort": 8000}]},
    }
    probe = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {"name": "probe", "namespace": NETWORK_NAMESPACE},
        "spec": {
            "containers": [
                {
                    "name": "probe",
                    "image": "docker.io/library/python:3.12.13-slim",
                    "command": ["python3", "-c", "import time; time.sleep(7200)"],
                }
            ]
        },
    }
    kube(
        "apply",
        "-f",
        "-",
        input=json.dumps(
            {"apiVersion": "v1", "kind": "List", "items": [service_account, role, binding, deployment, service, probe]}
        ),
    )
    wait_for(
        lambda: (
            inspect("get", "deployment", "traefik", "-n", NETWORK_NAMESPACE).get("status", {}).get("availableReplicas")
            == 1
        ),
        "Traefik did not become ready.",
    )
    wait_for(
        lambda: inspect("get", "pod", "probe", "-n", NETWORK_NAMESPACE).get("status", {}).get("phase") == "Running",
        "Network probe did not start.",
    )


def cleanup_network():
    kube("delete", "namespace", NETWORK_NAMESPACE, "--wait=true", "--timeout=120s", check=False)
    kube("delete", "clusterrolebinding,clusterrole", "medilab-286-traefik", check=False)


def http_status(url, host=""):
    code = """import sys,urllib.request,urllib.error
try:
 request=urllib.request.Request(sys.argv[1],headers={'Host':sys.argv[2]} if sys.argv[2] else {})
 r=urllib.request.urlopen(request,timeout=3)
 print(r.status)
except urllib.error.HTTPError as e: print(e.code)
except OSError: print(0)
"""
    return int(kube("exec", "-n", NETWORK_NAMESPACE, "probe", "--", "python3", "-c", code, url, host).stdout.strip())
