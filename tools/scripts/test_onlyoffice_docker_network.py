"""Observable reporting and ownership contracts for the disposable Docker proof."""

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import check_onlyoffice_docker_network as proof
import onlyoffice_network_report as report_output


class DockerNetworkProofTest(unittest.TestCase):
    @staticmethod
    def owned_directory(path):
        path = Path(path)
        path.mkdir(exist_ok=True)
        report_output.protect(path)
        return path

    def test_failure_report_is_sanitized_and_cleanup_still_runs(self):
        fake_host = SimpleNamespace(
            server_port=10000,
            serve_forever=lambda: None,
            shutdown=lambda: None,
            server_close=lambda: None,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = self.owned_directory(temporary)
            report = root / ".local" / "onlyoffice-docker-network.json"
            output = io.StringIO()
            with (
                patch.object(proof, "ROOT", root),
                patch.object(proof.sys, "argv", ["proof.py", "--report", str(report)]),
                patch.object(proof.bootstrap, "_assert_local_engine"),
                patch.object(proof, "ThreadingHTTPServer", return_value=fake_host),
                patch.object(proof.onlyoffice_tls, "prepare"),
                patch.object(
                    proof.Proof,
                    "run",
                    side_effect=RuntimeError("synthetic-private-value"),
                ),
                patch.object(proof.Proof, "cleanup") as cleanup,
                redirect_stdout(output),
                redirect_stderr(output),
                self.assertRaises(SystemExit) as result,
            ):
                proof.main()
            self.assertEqual(result.exception.code, 1)
            cleanup.assert_called_once()
            value = json.loads(report.read_text())
            self.assertFalse(value["passed"])
            self.assertTrue(value["owned_cleanup"])
            self.assertEqual(value["failure_type"], "RuntimeError")
            self.assertNotIn(
                "synthetic-private-value", report.read_text() + output.getvalue()
            )

    def refused_report(self, root, target):
        output = io.StringIO()
        with (
            patch.object(proof, "ROOT", root),
            patch.object(proof.sys, "argv", ["proof.py", "--report", str(target)]),
            patch.object(proof.bootstrap, "_assert_local_engine") as engine,
            patch.object(proof, "ThreadingHTTPServer") as host,
            patch.object(proof.Proof, "run") as run,
            redirect_stdout(output),
            redirect_stderr(output),
            self.assertRaises(SystemExit) as result,
        ):
            proof.main()
        self.assertEqual(result.exception.code, 1)
        engine.assert_not_called()
        host.assert_not_called()
        run.assert_not_called()
        self.assertNotIn(str(target), output.getvalue())

    def test_foreign_report_argument_is_rejected_before_engine_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.owned_directory(temporary)
            victim = root / "victim.json"
            victim.write_bytes(b"preserve foreign report")
            self.refused_report(root, victim)
            self.assertEqual(victim.read_bytes(), b"preserve foreign report")
            self.assertFalse((root / ".local").exists())

    def test_linked_report_parent_is_rejected_without_touching_victim(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = self.owned_directory(base / "checkout")
            victim = base / "victim"
            victim.mkdir()
            target = victim / "onlyoffice-docker-network.json"
            target.write_bytes(b"preserve linked report")
            if os.name == "nt":
                subprocess.run(
                    [
                        "cmd.exe",
                        "/d",
                        "/c",
                        "mklink",
                        "/J",
                        str(root / ".local"),
                        str(victim),
                    ],
                    capture_output=True,
                    check=True,
                )
            else:
                (root / ".local").symlink_to(victim, target_is_directory=True)
            self.refused_report(root, root / ".local" / target.name)
            self.assertEqual(target.read_bytes(), b"preserve linked report")
            if os.name == "nt":
                (root / ".local").rmdir()

    def test_nonregular_or_foreign_owned_report_is_rejected_before_engine(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.owned_directory(temporary)
            local = self.owned_directory(root / ".local")
            target = local / "onlyoffice-docker-network.json"
            target.mkdir()
            self.refused_report(root, target)
            target.rmdir()
            target.write_bytes(b"preserve foreign owner")
            with patch.object(
                report_output.FixedReport,
                "owned",
                side_effect=RuntimeError("foreign owner"),
            ):
                self.refused_report(root, target)
            self.assertEqual(target.read_bytes(), b"preserve foreign owner")

    def test_owner_guard_refuses_foreign_posix_and_windows_owners(self):
        target = Path("owned-report.json")
        with (
            patch.object(report_output.os, "name", "posix"),
            patch.object(report_output.os, "getuid", return_value=123, create=True),
            self.assertRaises(RuntimeError),
        ):
            report_output.FixedReport.owned(target, SimpleNamespace(st_uid=124))
        with (
            patch.object(report_output.os, "name", "nt"),
            patch.object(
                report_output.subprocess,
                "run",
                return_value=subprocess.CompletedProcess([], 1),
            ) as run,
            self.assertRaises(RuntimeError),
        ):
            report_output.FixedReport.owned(target, None)
        self.assertEqual(
            run.call_args.kwargs["env"]["MEDILAB_REPORT_OWNER_PATH"], str(target)
        )
        self.assertIn("-EncodedCommand", run.call_args.args[0])
        self.assertNotIn(str(target), run.call_args.args[0])

    def test_fixed_report_atomic_overwrite_and_failed_replace_preserve_old_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.owned_directory(temporary)
            target = root / ".local" / "onlyoffice-docker-network.json"
            writer = report_output.FixedReport(root, target)
            target.write_text('{"status":"not_run"}')
            report_output.protect(target)
            writer.write({"passed": True, "owned_cleanup": True})
            self.assertEqual(
                json.loads(target.read_text()), {"passed": True, "owned_cleanup": True}
            )
            previous = target.read_bytes()
            with (
                patch.object(
                    report_output.os, "replace", side_effect=OSError("replace failed")
                ),
                self.assertRaises(OSError),
            ):
                writer.write({"passed": False})
            self.assertEqual(target.read_bytes(), previous)
            self.assertEqual(list(target.parent.iterdir()), [target])

    def test_report_link_introduced_after_reservation_is_not_followed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.owned_directory(temporary)
            target = root / ".local" / "onlyoffice-docker-network.json"
            writer = report_output.FixedReport(root, target)
            victim = root / "victim.json"
            victim.write_bytes(b"preserve victim")
            metadata = victim.stat()
            linked = SimpleNamespace(st_mode=0o120777)
            original = Path.lstat

            def changed(path):
                return linked if path == target else original(path)

            with patch.object(Path, "lstat", changed), self.assertRaises(RuntimeError):
                writer.write({"passed": True})
            self.assertEqual(victim.read_bytes(), b"preserve victim")
            self.assertEqual(victim.stat(), metadata)

    def test_diagnostics_read_only_labeled_synthetic_peers_with_bounded_logs(self):
        fixture = proof.Proof()
        gateway = fixture.project + "-gateway"
        fixture.containers = [gateway, "foreign"]
        peers = [
            {
                "Config": {
                    "Labels": {proof.LABEL: fixture.owner},
                    "Env": ["NOT_FOR_REPORT=synthetic-private-value"],
                },
                "State": {"Status": "running", "ExitCode": 0},
                "NetworkSettings": {"Ports": {}},
            },
            {"Config": {"Labels": {proof.LABEL: "other-owner"}}},
        ]
        outputs = [
            subprocess.CompletedProcess([], 0, "x" * 4000, ""),
            subprocess.CompletedProcess(
                [], 0, '{"dns_resolved":true,"healthy":true,"status":200}', ""
            ),
        ]
        with (
            patch.object(proof, "inspect_optional", side_effect=peers),
            patch.object(proof, "command", side_effect=outputs) as command,
        ):
            fixture.diagnostics()
        self.assertEqual(len(fixture.report["synthetic_peers"]), 1)
        self.assertEqual(
            len(fixture.report["synthetic_peers"][0]["synthetic_log_tail"]), 2000
        )
        self.assertEqual(fixture.report["gateway_private_tls_probe"]["status"], 200)
        self.assertNotIn("synthetic-private-value", json.dumps(fixture.report))
        self.assertEqual(command.call_count, 2)
        self.assertTrue(all(gateway in call.args for call in command.call_args_list))

    def test_public_health_distinguishes_transport_and_http_failure(self):
        fixture = proof.Proof()
        with patch.object(
            proof, "host_get", side_effect=[None, (502, b""), (200, b"true")]
        ):
            self.assertFalse(fixture.public_health(12345))
            self.assertIsNone(fixture.report["candidate_public_http_status"])
            self.assertFalse(fixture.public_health(12345))
            self.assertEqual(fixture.report["candidate_public_http_status"], 502)
            self.assertTrue(fixture.public_health(12345))
            self.assertEqual(fixture.report["candidate_public_http_status"], 200)

    def test_gateway_origin_and_explicit_binding_are_fixed_before_start_without_restart(
        self,
    ):
        fixture = proof.Proof()
        expected_port = 43210
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            config_file = directory / "runtime.json"
            config_file.write_text(
                json.dumps(
                    {
                        "public_origin": "http://localhost:8080",
                        "bucket": "synthetic-proof",
                    }
                )
            )

            def create(*args):
                self.assertEqual(
                    json.loads(config_file.read_text()),
                    {
                        "public_origin": f"http://localhost:{expected_port}",
                        "bucket": "synthetic-proof",
                    },
                )
                self.assertEqual(args[-2:], ("-p", f"127.0.0.1:{expected_port}:8080"))
                return "owned-gateway"

            with (
                patch.object(proof.socket, "socket") as reserve,
                patch.object(
                    fixture, "container", side_effect=create
                ) as create_gateway,
                patch.object(proof, "command") as command,
                patch.object(
                    proof,
                    "inspect",
                    return_value={
                        "NetworkSettings": {
                            "Ports": {
                                "8080/tcp": [
                                    {
                                        "HostIp": "127.0.0.1",
                                        "HostPort": str(expected_port),
                                    }
                                ]
                            }
                        }
                    },
                ),
            ):
                reserve.return_value.__enter__.return_value.getsockname.return_value = (
                    "127.0.0.1",
                    expected_port,
                )
                result = fixture.start_gateway(directory, "base", "isolated", [], [])
            self.assertEqual(result, ("owned-gateway", expected_port))
            create_gateway.assert_called_once()
            command.assert_called_once_with(
                "network",
                "connect",
                "--alias",
                "onlyoffice-gateway",
                "isolated",
                "owned-gateway",
            )
            self.assertEqual(
                fixture.report["public_port_requested"],
                fixture.report["public_port_effective"],
            )

    def test_gateway_rejects_a_changed_effective_public_binding(self):
        fixture = proof.Proof()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "runtime.json").write_text(
                '{"public_origin":"http://localhost:8080"}'
            )
            with (
                patch.object(proof.socket, "socket") as reserve,
                patch.object(fixture, "container", return_value="owned-gateway"),
                patch.object(proof, "command"),
                patch.object(
                    proof,
                    "inspect",
                    return_value={
                        "NetworkSettings": {
                            "Ports": {
                                "8080/tcp": [
                                    {"HostIp": "127.0.0.1", "HostPort": "43211"}
                                ]
                            }
                        }
                    },
                ),
                self.assertRaises(RuntimeError),
            ):
                reserve.return_value.__enter__.return_value.getsockname.return_value = (
                    "127.0.0.1",
                    43210,
                )
                fixture.start_gateway(directory, "base", "isolated", [], [])

    def test_cleanup_refuses_foreign_label_and_continues_other_owned_resources(self):
        fixture = proof.Proof()
        fixture.containers = ["owned", "foreign"]
        values = [
            {"Config": {"Labels": {proof.LABEL: "another-owner"}}},
            {"Config": {"Labels": {proof.LABEL: fixture.owner}}},
            None,
        ]
        with (
            patch.object(proof, "inspect_optional", side_effect=values),
            patch.object(proof, "command") as command,
            self.assertRaises(RuntimeError),
        ):
            fixture.cleanup()
        self.assertEqual(command.call_args.args, ("rm", "-f", "owned"))
        self.assertEqual(fixture.report["cleanup_failures"], 1)

    def test_typed_missing_cleanup_result_does_not_hide_operational_errors(self):
        name = "medilab-onlyoffice-proof-fixture-isolated"
        for message in (
            f"Error response from daemon: network {name} not found",
            f"Error: No such network: {name}",
        ):
            with patch.object(
                proof,
                "command",
                return_value=subprocess.CompletedProcess([], 1, "[]", message),
            ):
                self.assertIsNone(proof.inspect_optional("network", name))
        for message in (
            "cannot connect to daemon",
            f"permission denied: network {name} not found",
            "Error response from daemon: network another-project not found",
        ):
            with (
                self.subTest(message=message),
                patch.object(
                    proof,
                    "command",
                    return_value=subprocess.CompletedProcess([], 1, "[]", message),
                ),
                self.assertRaises(RuntimeError),
            ):
                proof.inspect_optional("network", name)

    def test_old_server_failure_preserves_observed_version_without_resource_creation(
        self,
    ):
        fixture = proof.Proof()
        with (
            patch.object(
                proof,
                "command",
                return_value=subprocess.CompletedProcess(
                    [], 0, '{"ServerVersion":"27.5.1"}', ""
                ),
            ) as command,
            self.assertRaises(RuntimeError),
        ):
            fixture.run(Path("unused"), 1)
        self.assertEqual(fixture.report["server_version"], "27.5.1")
        self.assertEqual(command.call_count, 1)
        self.assertEqual(fixture.networks, [])
        self.assertEqual(fixture.containers, [])

    def test_cleanup_tracks_create_intent_before_unknown_commit_failure(self):
        fixture = proof.Proof()
        with (
            patch.object(proof, "command", side_effect=RuntimeError("unknown commit")),
            self.assertRaises(RuntimeError),
        ):
            fixture.network("isolated", "--internal")
        self.assertEqual(fixture.networks, [fixture.project + "-isolated"])


if __name__ == "__main__":
    unittest.main()
