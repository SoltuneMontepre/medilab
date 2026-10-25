"""Drift checks use process-bound effective policy rather than a parent environment declaration."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import inspect_config

ROOT = Path(__file__).resolve().parent


class TestInspectConfig(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.processes = self.directory / "proc"
        self.reports = self.directory / "reports"
        self.processes.mkdir()
        self.reports.mkdir()
        self.settings = self.directory / "settings.json"
        self.settings.write_bytes((ROOT / "settings.json").read_bytes())
        self.expected = json.loads(self.settings.read_bytes())
        self.add_worker("docservice", 101)
        self.add_worker("converter", 102)

    def add_worker(self, name, pid):
        process = self.processes / str(pid)
        process.mkdir()
        (process / "comm").write_text(name + "\n")
        (process / "stat").write_text(f"{pid} ({name}) " + " ".join(["S"] + ["0"] * 18 + ["123456"]))
        (process / "environ").write_bytes(
            b"NODE_ENV=production-linux\0NODE_CONFIG_DIR=/etc/onlyoffice/documentserver\0NODE_CONFIG="
            + self.settings.read_bytes()
            + b"\0SECRET=must-not-be-reported\0"
        )
        report = {
            "worker": name,
            "pid": pid,
            "startTicks": "123456",
            "binarySha256": inspect_config.BINARIES[name],
            "settingsSha256": hashlib.sha256(self.settings.read_bytes()).hexdigest(),
            "policy": inspect_config.selected_policy(self.expected),
        }
        (self.reports / f"{name}-{pid}.json").write_text(json.dumps(report))

    def inspect(self):
        return inspect_config.inspect_workers(self.settings, self.reports, self.processes)

    def test_all_native_workers_and_converter_children_require_attestation(self):
        self.add_worker("converter", 103)
        reports = self.inspect()
        self.assertEqual({report["pid"] for report in reports}, {101, 102, 103})
        self.assertNotIn("must-not-be-reported", json.dumps(reports))
        (self.reports / "converter-103.json").unlink()
        with self.assertRaises(FileNotFoundError):
            self.inspect()

    def test_parent_config_without_effective_attestation_is_refused(self):
        (self.reports / "docservice-101.json").unlink()
        with self.assertRaises(FileNotFoundError):
            self.inspect()

    def test_stale_report_from_reused_pid_is_refused(self):
        path = self.processes / "101" / "stat"
        path.write_text(path.read_text().replace("123456", "654321"))
        with self.assertRaises(RuntimeError):
            self.inspect()

    def test_effective_policy_drift_is_refused_despite_correct_environment(self):
        path = self.reports / "docservice-101.json"
        report = json.loads(path.read_text())
        report["policy"]["callbackRequestTimeout"]["wholeCycle"] = "10m"
        path.write_text(json.dumps(report))
        with self.assertRaises(RuntimeError):
            self.inspect()

    def test_settings_changed_without_worker_restart_are_refused(self):
        self.settings.write_text(self.settings.read_text().replace("604800", "86400"))
        with self.assertRaises(RuntimeError):
            self.inspect()

    def test_missing_config_or_worker_is_refused(self):
        (self.processes / "101" / "environ").write_bytes(b"NODE_ENV=production-linux\0")
        with self.assertRaises((RuntimeError, KeyError)):
            self.inspect()
        (self.processes / "101" / "comm").write_text("unrelated\n")
        with self.assertRaises(RuntimeError):
            self.inspect()


if __name__ == "__main__":
    unittest.main()
