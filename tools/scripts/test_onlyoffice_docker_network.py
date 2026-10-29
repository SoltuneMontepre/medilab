"""Observable reporting and ownership contracts for the disposable Docker proof."""

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import check_onlyoffice_docker_network as proof


class DockerNetworkProofTest(unittest.TestCase):
    def test_failure_report_is_sanitized_and_cleanup_still_runs(self):
        fake_host = SimpleNamespace(
            server_port=10000,
            serve_forever=lambda: None,
            shutdown=lambda: None,
            server_close=lambda: None,
        )
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "result.json"
            output = io.StringIO()
            with (
                patch.object(proof.sys, "argv", ["proof.py", "--report", str(report)]),
                patch.object(proof.bootstrap, "_assert_local_engine"),
                patch.object(proof, "ThreadingHTTPServer", return_value=fake_host),
                patch.object(proof.threading, "Thread"),
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
