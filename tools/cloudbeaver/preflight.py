"""Read-only CloudBeaver preflight. Requires an explicitly selected, authorized Kubernetes context.

Usage: python3 tools/cloudbeaver/preflight.py --context CONTEXT [--kubeconfig PATH]
Optional account inventory uses an existing approved Netscape session cookie file; no login is attempted.
Never opens H2 content, decodes passwords, changes resources or prints raw logs/configuration.
"""

import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys

from preflight_inventory import inventory
from preflight_storage import METADATA_COMMAND, workspace_consumers, workspace_metadata


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def identifier(value):
    return {
        "present": bool(value),
        "reserved_team": value.lower() in {"admin", "user"},
        "normalized": value == value.strip().lower(),
    }


class Preflight:
    def __init__(self, args):
        self.args = args
        self.prefix = ["kubectl", "--context", args.context, "--request-timeout=10s"]
        if args.kubeconfig:
            self.prefix += ["--kubeconfig", args.kubeconfig]

    def run(self, *args, optional=False):
        result = subprocess.run([*self.prefix, *args], text=True, capture_output=True, timeout=20, check=False)
        if result.returncode:
            if optional:
                return None
            categories = [
                name
                for name in ("Forbidden", "Unauthorized", "no context exists", "connection refused", "not found")
                if name.lower() in result.stderr.lower()
            ]
            if "context" in result.stderr.lower() and "does not exist" in result.stderr.lower():
                categories.append("selected context absent")
            raise RuntimeError("Kubernetes access failed: " + (", ".join(categories) or "request unavailable"))
        return result.stdout

    def get(self, kind, name=None, namespace=None, optional=False):
        args = ["get", kind]
        if name:
            args.append(name)
        if namespace:
            args += ["-n", namespace]
        value = self.run(*args, "-o", "json", optional=optional)
        return json.loads(value) if value else None

    def inspect(self):
        namespace = self.args.namespace
        deployment = self.get("deployment", "cloudbeaver", namespace)
        template = deployment["spec"]["template"]
        result = {
            "context": self.args.context,
            "namespace": namespace,
            "production_changes": False,
            "deployment": {
                "uid": deployment["metadata"]["uid"],
                "generation": deployment["metadata"]["generation"],
                "replicas": deployment["spec"].get("replicas"),
                "strategy": deployment["spec"].get("strategy"),
                "template_sha256": digest(template),
                "management_sync_configured": any(
                    env["name"] == "CLOUDBEAVER_DB_URL" and env.get("value", "").endswith(";WRITE_DELAY=0")
                    for container in template["spec"]["containers"]
                    for env in container.get("env", [])
                ),
                "containers": [
                    {
                        "name": c["name"],
                        "image": c["image"],
                        "env_names": [e["name"] for e in c.get("env", [])],
                        "mounts": c.get("volumeMounts", []),
                        "env_references": [
                            {"name": e["name"], "value_from": e.get("valueFrom")} for e in c.get("env", [])
                        ],
                        "readiness_present": "readinessProbe" in c,
                        "security_context": c.get("securityContext", {}),
                    }
                    for c in template["spec"]["containers"]
                ],
            },
        }
        pods = self.get("pods", namespace=namespace)["items"]
        result["workspace_consumers"] = workspace_consumers(pods, "cloudbeaver-workspace")
        pods = [pod for pod in pods if pod["metadata"].get("labels", {}).get("app.kubernetes.io/name") == "cloudbeaver"]
        result["pods"] = [
            {
                "name": pod["metadata"]["name"],
                "uid": pod["metadata"]["uid"],
                "phase": pod.get("status", {}).get("phase"),
                "conditions": pod.get("status", {}).get("conditions", []),
                "containers": [
                    {key: status.get(key) for key in ("name", "ready", "restartCount", "imageID")}
                    for status in pod.get("status", {}).get("containerStatuses", [])
                ],
            }
            for pod in pods
        ]
        result["pod_security_context"] = template["spec"].get("securityContext", {})
        events = self.get("events", namespace=namespace, optional=True)
        result["events"] = [
            {key: event.get(key) for key in ("type", "reason", "count", "firstTimestamp", "lastTimestamp")}
            for event in (events or {}).get("items", [])
            if event.get("involvedObject", {}).get("uid") in {pod["metadata"]["uid"] for pod in pods}
        ]
        for pod in result["pods"]:
            pod["conditions"] = [
                {key: value.get(key) for key in ("type", "status", "reason", "lastTransitionTime")}
                for value in pod["conditions"]
            ]
        application = self.get("application.argoproj.io", "cloudbeaver", "argocd", optional=True)
        result["argocd"] = {"available": bool(application)}
        if application:
            result["argocd"].update(
                {
                    "sync": {
                        key: application.get("status", {}).get("sync", {}).get(key) for key in ("status", "revision")
                    },
                    "health": application.get("status", {}).get("health", {}).get("status"),
                    "automated": application["spec"].get("syncPolicy", {}).get("automated"),
                }
            )
        external = self.get("externalsecret", "cloudbeaver-admin", namespace, optional=True)
        result["external_secret"] = [
            {key: condition.get(key) for key in ("type", "status", "reason", "lastTransitionTime")}
            for condition in (external or {}).get("status", {}).get("conditions", [])
        ]
        keys = self.run(
            "get",
            "secret",
            "cloudbeaver-admin",
            "-n",
            namespace,
            "-o",
            'go-template={{range $k, $v := .data}}{{$k}}{{"\\n"}}{{end}}',
            optional=True,
        )
        result["admin_secret_keys"] = keys.splitlines() if keys is not None else None
        name = self.run(
            "get",
            "secret",
            "cloudbeaver-admin",
            "-n",
            namespace,
            "-o",
            'go-template={{index .data "CB_ADMIN_NAME"}}',
            optional=True,
        )
        secret_name = base64.b64decode(name).decode() if name and name != "<no value>" else ""
        result["secret_bootstrap_identifier"] = identifier(secret_name)
        pvc = self.get("pvc", "cloudbeaver-workspace", namespace)
        result["pvc"] = {
            "uid": pvc["metadata"]["uid"],
            "name": pvc["metadata"]["name"],
            "phase": pvc.get("status", {}).get("phase"),
            "volume": pvc["spec"].get("volumeName"),
            "storage_class": pvc["spec"].get("storageClassName"),
            "protection": pvc["metadata"].get("annotations", {}).get("argocd.argoproj.io/sync-options"),
        }
        if pvc["spec"].get("volumeName"):
            pv = self.get("pv", pvc["spec"]["volumeName"], optional=True)
            result["pv"] = {
                "uid": (pv or {}).get("metadata", {}).get("uid"),
                "reclaim_policy": (pv or {}).get("spec", {}).get("persistentVolumeReclaimPolicy"),
                "claim_uid_matches": (pv or {}).get("spec", {}).get("claimRef", {}).get("uid")
                == pvc["metadata"]["uid"],
                "node_affinity_sha256": digest((pv or {}).get("spec", {}).get("nodeAffinity")),
            }
        result["workspace"] = {"available": False}
        running = next(
            (
                pod
                for pod in pods
                if any(
                    c.get("name") == "cloudbeaver" and c.get("state", {}).get("running")
                    for c in pod.get("status", {}).get("containerStatuses", [])
                )
            ),
            None,
        )
        if running:
            pod_name = running["metadata"]["name"]
            prefix = ["exec", "-n", namespace, pod_name, "-c", "cloudbeaver", "--"]
            value = self.run(*prefix, "/bin/bash", "-c", 'printf %s "${CB_ADMIN_NAME-}"', optional=True)
            result["pod_bootstrap_identifier"] = {
                **identifier(value or ""),
                "matches_current_secret": value == secret_name,
            }
            # Runtime JSON is captured only in memory; H2 files are stat'ed, never read or opened.
            metadata = self.run(
                *prefix,
                "/bin/bash",
                "-c",
                METADATA_COMMAND,
                optional=True,
            )
            runtime = self.run(*prefix, "cat", "workspace/.data/.cloudbeaver.runtime.conf", optional=True)
            result["workspace"] = {
                **workspace_metadata(metadata),
                "runtime_present": runtime is not None,
            }
            mount = self.run(
                *prefix,
                "/bin/bash",
                "-c",
                "awk '$5 == \"/opt/cloudbeaver/workspace\" {print $5}' /proc/self/mountinfo",
                optional=True,
            )
            result["workspace"]["workspace_is_mountpoint"] = bool(mount and mount.strip())
            try:
                settings = json.loads(runtime)
                server_name = settings.get("server", {}).get("serverName")
                result["workspace"].update(
                    {
                        "runtime_json_valid": True,
                        "server_name_present": isinstance(server_name, str) and bool(server_name.strip()),
                    }
                )
            except (TypeError, ValueError, AttributeError):
                result["workspace"]["runtime_json_valid"] = False
            patterns = {
                "configuration_mode": "Server is in configuration mode!",
                "management_database_opened": "Management database connection established",
                "autoconfiguration_failed": "Error loading server auto configuration",
                "subject_collision": "User or team '.*' already exists",
                "runtime_save_attempted": "Saving runtime configuration",
                "synchronous_management_url": "Initiate connection pool.*WRITE_DELAY=0",
            }
            result["startup_log_counts"] = {}
            for previous in (False, True):
                logs = self.run(
                    "logs",
                    "-n",
                    namespace,
                    pod_name,
                    "-c",
                    "cloudbeaver",
                    "--tail=2000",
                    *(["--previous"] if previous else []),
                    optional=True,
                )
                result["startup_log_counts"]["previous" if previous else "current"] = (
                    None if logs is None else {key: len(re.findall(pattern, logs)) for key, pattern in patterns.items()}
                )
        result["accounts"] = {
            "verified": False,
            "reason": "No existing approved application session supplied; never inspect live H2 directly.",
        }
        if self.args.session_cookie_file:
            result["accounts"] = inventory(self.args.session_cookie_file, secret_name)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--kubeconfig")
    parser.add_argument("--namespace", default="medilab")
    parser.add_argument("--session-cookie-file")
    args = parser.parse_args()
    try:
        sys.stdout.write(json.dumps(Preflight(args).inspect(), indent=2) + "\n")
    except Exception as error:
        # Do not render exception text from HTTP/subprocess/JSON libraries: it can contain sensitive payloads.
        category = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        sys.stdout.write(json.dumps({"blocked": True, "reason": category, "production_changes": False}) + "\n")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
