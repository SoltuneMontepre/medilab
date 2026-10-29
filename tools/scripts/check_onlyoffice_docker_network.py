"""Prove local Docker bridge isolation and the actual editor proxy using disposable fixtures."""

import argparse
import http.client
import json
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import demo_bootstrap as bootstrap
import onlyoffice_tls
from host_tools import assert_onlyoffice_engine
from onlyoffice_network_fixture import (
    BACKEND,
    BASELINE_PUBLIC,
    DS,
    GATEWAY,
    IMAGE,
    LABEL,
    PROBE,
    certificate_variant,
    host_get,
    websocket,
)
from onlyoffice_network_report import FixedReport
from onlyoffice_state import assert_network_policy, network_driver_options

ROOT = Path(__file__).resolve().parents[2]


RUNTIME_FILE = "runtime.json"


def command(*arguments, check=True, timeout=120):
    result = subprocess.run(
        ["docker", *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )
    if check and result.returncode:
        raise RuntimeError(
            f"Docker proof operation {arguments[:2]} failed ({result.returncode})"
        )
    return result


def inspect(kind, name):
    return json.loads(command(kind, "inspect", name).stdout)[0]


def inspect_optional(kind, name):
    result = command(kind, "inspect", name, check=False, timeout=30)
    if result.returncode:
        target = re.escape(name)
        missing = rf"(?:Error(?::| response from daemon:)\s*)?(?:No such (?:{kind}|object):\s*{target}|network {target} not found)"
        if re.fullmatch(missing, result.stderr.strip(), flags=re.IGNORECASE):
            return None
        raise RuntimeError("The Docker proof could not verify its owned cleanup target")
    return json.loads(result.stdout)[0]


def wait(check, timeout=30):
    deadline = time.monotonic() + timeout
    while True:
        try:
            answer = check()
            if answer:
                return answer
        except (OSError, RuntimeError, ValueError, http.client.HTTPException):
            pass
        if time.monotonic() > deadline:
            raise RuntimeError(
                "The synthetic Docker positive control did not become ready"
            )
        time.sleep(0.1)


def _remove_owned_proof_resource(kind, name, owner):
    value = inspect_optional(kind, name)
    if not value:
        return
    labels = value["Config"]["Labels"] if kind == "container" else value["Labels"]
    if labels.get(LABEL) != owner:
        raise RuntimeError("Docker proof refused to remove a foreign resource")
    if kind == "container":
        command("rm", "-f", name, timeout=30)
    else:
        command("network", "rm", name, timeout=30)
    if inspect_optional(kind, name):
        raise RuntimeError("The owned Docker proof resource was not removed")


class Proof:
    def __init__(self):
        self.owner = uuid.uuid4().hex
        self.project = "medilab-onlyoffice-proof-" + self.owner[:12]
        self.containers = []
        self.networks = []
        self.report = {
            "passed": False,
            "stage": "engine-preflight",
            "server_version": None,
        }

    def network(self, suffix, *options):
        name = self.project + "-" + suffix
        self.networks.append(name)
        command("network", "create", "--label", f"{LABEL}={self.owner}", *options, name)
        return name

    def container(self, suffix, network, code, *options):
        name = self.project + "-" + suffix
        self.containers.append(name)
        command(
            "run",
            "-d",
            "--name",
            name,
            "--label",
            f"{LABEL}={self.owner}",
            "--network",
            network,
            *options,
            IMAGE,
            "python",
            "-B",
            "-c",
            code,
        )
        return name

    def probe(self, container, targets):
        return json.loads(
            command(
                "exec", container, "python", "-c", PROBE, json.dumps(targets)
            ).stdout
        )

    def diagnostics(self):
        peers = []
        for name in self.containers:
            try:
                value = inspect_optional("container", name)
                if not value or value["Config"]["Labels"].get(LABEL) != self.owner:
                    continue
                logs = command("logs", "--tail", "8", name, check=False, timeout=10)
                peers.append(
                    {
                        "role": name.removeprefix(self.project + "-"),
                        "status": value.get("State", {}).get("Status"),
                        "exit_code": value.get("State", {}).get("ExitCode"),
                        "published": value.get("NetworkSettings", {}).get("Ports"),
                        "synthetic_log_tail": (logs.stdout + logs.stderr)[-2000:],
                    }
                )
                if name == self.project + "-gateway":
                    script = "import json,http.client,ssl,socket;d={}\ntry:\n d['dns_resolved']=bool(socket.getaddrinfo('onlyoffice',443));c=http.client.HTTPSConnection('onlyoffice',443,timeout=3,context=ssl.create_default_context(cafile='/run/onlyoffice-ca/ca.crt'));c.request('GET','/healthcheck');r=c.getresponse();d.update(status=r.status,healthy=r.read()==b'true')\nexcept OSError as e:d.update(error_type=type(e).__name__,errno=e.errno,verify_code=getattr(e,'verify_code',None))\nprint(json.dumps(d))"
                    probe = command(
                        "exec", name, "python", "-c", script, check=False, timeout=10
                    )
                    self.report["gateway_private_tls_probe"] = (
                        json.loads(probe.stdout)
                        if probe.returncode == 0
                        else {"exec_exit": probe.returncode}
                    )
            except (
                OSError,
                RuntimeError,
                ValueError,
                KeyError,
                subprocess.SubprocessError,
            ):
                self.report["diagnostic_unavailable"] = True
        self.report["synthetic_peers"] = peers

    def public_health(self, port):
        response = host_get(port)
        self.report["candidate_public_http_status"] = response[0] if response else None
        return response == (200, b"true")

    def cleanup(self):
        failures = 0
        for kind, names in (("container", self.containers), ("network", self.networks)):
            for name in reversed(names):
                try:
                    _remove_owned_proof_resource(kind, name, self.owner)
                except (
                    RuntimeError,
                    OSError,
                    ValueError,
                    KeyError,
                    subprocess.SubprocessError,
                ):
                    failures += 1
        self.report["cleanup_failures"] = failures
        if failures:
            raise RuntimeError(
                "The synthetic Docker cleanup could not verify all owned resources"
            )

    def start_gateway(self, directory, base, isolated, cert, common):
        with socket.socket() as reserve:
            reserve.bind(("127.0.0.1", 0))
            public_port = reserve.getsockname()[1]
        config_file = directory / RUNTIME_FILE
        config = json.loads(config_file.read_text())
        config["public_origin"] = f"http://localhost:{public_port}"
        config_file.write_text(json.dumps(config))
        gateway = self.container(
            "gateway",
            base,
            GATEWAY,
            *cert,
            *common,
            "-e",
            "ONLYOFFICE_PROXY_ROLE=gateway",
            "-p",
            f"127.0.0.1:{public_port}:8080",
        )
        command(
            "network", "connect", "--alias", "onlyoffice-gateway", isolated, gateway
        )
        binding = inspect("container", gateway)["NetworkSettings"]["Ports"]["8080/tcp"]
        expected = [{"HostIp": "127.0.0.1", "HostPort": str(public_port)}]
        if binding != expected:
            raise RuntimeError(
                "The synthetic gateway did not retain its explicitly requested loopback port"
            )
        self.report.update(
            public_port_requested=public_port,
            public_port_effective=int(binding[0]["HostPort"]),
        )
        return gateway, public_port

    def run(self, directory, listener_port):
        info = json.loads(command("info", "--format", "{{json .}}").stdout)
        if "host" in info:
            raise RuntimeError(
                "This proof requires real Docker, not the Podman compatibility CLI"
            )
        version = info["ServerVersion"]
        self.report["server_version"] = version
        assert_onlyoffice_engine(info)
        self.report["stage"] = "create-synthetic-topology"
        command("image", "pull", IMAGE)
        base = self.network("base")
        plain = self.network("plain", "--internal")
        options = [
            item
            for key, value in network_driver_options("docker").items()
            for item in ("--opt", f"{key}={value}")
        ]
        isolated = self.network("isolated", "--internal", *options)
        assert_network_policy(inspect("network", isolated), "docker")
        base_gateway = inspect("network", base)["IPAM"]["Config"][0]["Gateway"]
        plain_gateway = inspect("network", plain)["IPAM"]["Config"][0]["Gateway"]
        cert = [
            "--mount",
            f"type=bind,src={directory / 'tls/server'},dst=/run/onlyoffice-tls,readonly",
        ]
        common = [
            "--mount",
            f"type=bind,src={ROOT / 'tools/onlyoffice'},dst=/opt/onlyoffice,readonly",
            "--mount",
            f"type=bind,src={directory / 'runtime.json'},dst=/run/onlyoffice-config/runtime.json,readonly",
            "--mount",
            f"type=bind,src={directory / 'tls/public'},dst=/run/onlyoffice-ca,readonly",
            "-e",
            "PYTHONPATH=/opt/onlyoffice",
        ]
        with socket.socket() as reserve:
            reserve.bind(("127.0.0.1", 0))
            baseline_port = reserve.getsockname()[1]
        baseline = self.container(
            "baseline",
            plain,
            DS,
            *cert,
            "--network-alias",
            "onlyoffice",
            "-p",
            f"127.0.0.1:{baseline_port}:8080",
        )
        self.container(
            "baseline-adapter", "container:" + baseline, BASELINE_PUBLIC, *common
        )
        internal_http = "import http.client,json;c=http.client.HTTPConnection('127.0.0.1',8080,timeout=3);c.request('GET','/healthcheck',headers={'Host':'localhost:8080'});r=c.getresponse();print(json.dumps(r.status==200 and r.read()==b'true'))"
        wait(
            lambda: json.loads(
                command("exec", baseline, "python", "-c", internal_http).stdout
            )
        )
        host_control = "import http.client,json,sys;c=http.client.HTTPConnection(sys.argv[1],int(sys.argv[2]),timeout=3);c.request('GET','/');r=c.getresponse();print(json.dumps(r.status==200 and r.read().decode()==sys.argv[3]))"
        baseline_host = wait(
            lambda: json.loads(
                command(
                    "exec",
                    baseline,
                    "python",
                    "-c",
                    host_control,
                    plain_gateway,
                    str(listener_port),
                    self.owner,
                ).stdout
            )
        )
        baseline_response = host_get(baseline_port, authority="localhost:8080")
        if baseline_response is not None and baseline_response != (200, b"true"):
            raise RuntimeError(
                "The baseline public request reached an unexpected authority or handler"
            )
        baseline_public = baseline_response == (200, b"true")
        self.report.update(
            plain_internal_host_reachable=baseline_host,
            plain_internal_listener_healthy_inside=True,
            plain_internal_published_http=baseline_public,
            stage="candidate-public-proxy",
        )
        backend = self.container(
            "backend",
            base,
            BACKEND,
            "--network-alias",
            "garage",
            "--network-alias",
            "odoo",
        )
        backend_ip = inspect("container", backend)["NetworkSettings"]["Networks"][base][
            "IPAddress"
        ]
        ds = self.container("ds", isolated, DS, *cert, "--network-alias", "onlyoffice")
        gateway, public_port = self.start_gateway(
            directory, base, isolated, cert, common
        )
        adapter = self.container(
            "adapter",
            "container:" + ds,
            GATEWAY,
            *common,
            "-e",
            "ONLYOFFICE_PROXY_ROLE=adapter",
        )
        wait(lambda: self.public_health(public_port))
        public_denied = host_get(public_port, "/ConvertService.ashx") == (400, b"")
        targets = [(backend_ip, p) for p in (3900, 3903, 5432, 8069, 8978)] + [
            (base_gateway, listener_port),
            (plain_gateway, listener_port),
            ("169.254.169.254", 80),
        ]
        wait(lambda: all(self.probe(gateway, targets[:-1])))
        self.report["stage"] = "candidate-host-backend-denial"
        denied = self.probe(ds, targets)
        if any(denied):
            raise RuntimeError(
                "The isolated Document Server namespace reached a denied host/backend destination"
            )
        if not public_denied:
            raise RuntimeError("The public editor proxy exposed conversion commands")
        tls = "import http.client,ssl,json;c=http.client.HTTPSConnection('onlyoffice-gateway',9443,context=ssl.create_default_context(cafile='/run/onlyoffice-ca/ca.crt'),timeout=5);c.request('GET','/healthcheck');r=c.getresponse();print(json.dumps({'ok':r.status==200 and r.read()==b'true'}))"
        if json.loads(command("exec", gateway, "python", "-c", tls).stdout) != {
            "ok": True
        }:
            raise RuntimeError(
                "The existing internal TLS proxy failed its positive control"
            )
        self.report["stage"] = "verified-tls-negatives"
        certificate = directory / "tls/server/tls.crt"
        original = certificate.read_bytes()
        try:
            for trusted, hostname in (
                (False, "onlyoffice"),
                (True, "wrong.synthetic.invalid"),
            ):
                certificate.write_bytes(
                    certificate_variant(directory, trusted, hostname)
                )
                wait(lambda: host_get(public_port) == (502, b""))
                certificate.write_bytes(original)
                wait(lambda: host_get(public_port) == (200, b"true"))
        finally:
            certificate.write_bytes(original)
        storage = "import http.client,json;c=http.client.HTTPConnection('127.0.0.1',3900,timeout=5);c.request('GET','/synthetic-proof/immutable-marker',headers={'Host':'localhost:3900'});r=c.getresponse();print(json.dumps(r.status==200 and r.read()==b'owned-docker-proof'))"
        wait(lambda: json.loads(command("exec", ds, "python", "-c", storage).stdout))
        callback = "import http.client,ssl,json;c=http.client.HTTPSConnection('onlyoffice-gateway',7443,context=ssl.create_default_context(cafile='/run/onlyoffice-ca/ca.crt'),timeout=5);c.request('POST','/medilab/laboratory-files/callback/'+('0'*64),body='{}',headers={'Content-Type':'application/json'});r=c.getresponse();print(json.dumps(r.status==403 and json.loads(r.read())=={'error':1}))"
        if (
            json.loads(command("exec", adapter, "python", "-c", callback).stdout)
            is not True
        ):
            raise RuntimeError(
                "The actual TLS gateway callback route did not reach its refusing synthetic backend"
            )
        self.report["stage"] = "websocket-duplex"
        websocket(public_port, self.owner)
        binding = inspect("container", gateway)["NetworkSettings"]["Ports"]["8080/tcp"]
        if (
            len(binding) != 1
            or binding[0]["HostIp"] != "127.0.0.1"
            or inspect("container", ds)["HostConfig"].get("PortBindings")
        ):
            raise RuntimeError(
                "The synthetic topology exposed an unexpected public binding"
            )
        return {
            "engine": version,
            "plain_internal_host_reachable": baseline_host,
            "plain_internal_listener_healthy_inside": True,
            "plain_internal_published_http": baseline_public,
            "isolated_public_via_gateway": True,
            "public_conversion_refused": True,
            "gateway_positive_controls": len(targets) - 1,
            "ds_denied_targets": len(targets),
            "internal_verified_tls": True,
            "wrong_ca_refused": True,
            "wrong_san_refused": True,
            "websocket_duplex_roundtrips": 2,
            "loopback_storage_tls_route": True,
            "public_binding_loopback_only": True,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    arguments = parser.parse_args()
    report = None
    proof = Proof()
    host = None
    failure = False

    class Host(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            # The synthetic listener must not log verification paths or request metadata.
            return

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(proof.owner.encode())

    try:
        if arguments.report is not None:
            report = FixedReport(ROOT, arguments.report)
        bootstrap._assert_local_engine()
        host = ThreadingHTTPServer(("0.0.0.0", 0), Host)
        threading.Thread(target=host.serve_forever, daemon=True).start()
        with tempfile.TemporaryDirectory(
            prefix="medilab-onlyoffice-docker-proof-"
        ) as temporary:
            directory = Path(temporary)
            directory.chmod(0o700)
            onlyoffice_tls.prepare(directory, proof.project, proof.owner)
            (directory / RUNTIME_FILE).write_text(
                json.dumps(
                    {
                        "format": 1,
                        "public_origin": "http://localhost:8080",
                        "storage_origin": "http://localhost:3900",
                        "storage_port": 3900,
                        "http_port": 8080,
                        "bucket": "synthetic-proof",
                    }
                )
            )
            try:
                proof.report.update(proof.run(directory, host.server_port))
            except (
                OSError,
                RuntimeError,
                ValueError,
                KeyError,
                TypeError,
                subprocess.SubprocessError,
                http.client.HTTPException,
            ):
                proof.diagnostics()
                raise
            finally:
                previous = proof.report["stage"]
                proof.report["stage"] = "owned-fixture-cleanup"
                proof.cleanup()
                proof.report.update(owned_cleanup=True, stage=previous)
        proof.report.update(passed=True, stage="completed")
    except (
        OSError,
        RuntimeError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
        http.client.HTTPException,
    ) as error:
        failure = True
        proof.report.update(failure_type=type(error).__name__)
        print(
            "The synthetic Docker network/proxy proof failed; inspect its sanitized report.",
            file=sys.stderr,
        )
    finally:
        if host:
            host.shutdown()
            host.server_close()
        if report is not None:
            try:
                report.write(proof.report)
            except (OSError, RuntimeError, subprocess.SubprocessError):
                failure = True
                proof.report.update(passed=False, failure_type="ReportWriteError")
                print(
                    "The fixed Docker proof report could not be written safely.",
                    file=sys.stderr,
                )
        print(json.dumps(proof.report, sort_keys=True))
    raise SystemExit(1 if failure else 0)


if __name__ == "__main__":
    main()
