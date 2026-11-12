"""Regression tests for the origin isolation check without a cluster."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/scripts/check_origin_isolation.sh"
KUBECTL = r"""#!/usr/bin/env python3
import json
import os
import pathlib
import sys

args = sys.argv[1:]
state = pathlib.Path(os.environ["PROBE_STATE"])
scenario = os.environ["PROBE_SCENARIO"]
if "run" in args:
    if scenario == "pending":
        sys.exit(1)
    code = {"unavailable": 7, "dns": 6, "reached": 0}.get(scenario, 28)
    if scenario == "partial" and any(":8069/" in arg for arg in args):
        code = 0
    print(f"curl-exit={code}")
elif "rollout" in args or "rollout/odoo" in args:
    if scenario == "unhealthy":
        sys.exit(1)
elif "create" in args:
    manifest = sys.stdin.read()
    lines = manifest.splitlines()
    source = next(line.split(":", 1)[1].strip() for line in lines if "app.kubernetes.io/name:" in line)
    probes = json.loads(state.read_text()) if state.exists() else []
    name = f"origin-check-{len(probes)}"
    probes.append({"name": name, "source": source, "manifest": manifest, "deleted": False})
    state.write_text(json.dumps(probes))
    print(name, end="")
elif "wait" in args:
    if scenario == "pending":
        sys.exit(1)
elif "logs" in args:
    name = next(arg.split("/", 1)[1] for arg in args if arg.startswith("job/"))
    probe = next(probe for probe in json.loads(state.read_text()) if probe["name"] == name)
    allowed = probe["source"] in ("cloudflared", "traefik")
    if scenario == "unavailable":
        print("curl-exit=7")
    elif scenario == "dns":
        print("curl-exit=6")
    elif scenario == "reached" and not allowed:
        print("curl-exit=0")
    elif scenario == "partial" and probe["name"] == "origin-check-3":
        print("curl-exit=0")
    elif scenario == "refused" and not allowed:
        print("curl-exit=7")
    else:
        print("curl-exit=0" if allowed else "curl-exit=28")
elif "delete" in args:
    name = args[args.index("job") + 1]
    probes = json.loads(state.read_text())
    next(probe for probe in probes if probe["name"] == name)["deleted"] = True
    state.write_text(json.dumps(probes))
else:
    sys.exit(2)
"""


@unittest.skipUnless(shutil.which("bash"), "The cluster check requires Bash.")
class OriginIsolationTests(unittest.TestCase):
    def run_check(self, scenario):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kubectl = root / "kubectl"
            kubectl.write_text(KUBECTL)
            kubectl.chmod(0o755)
            state = root / "probes.json"
            env = os.environ | {
                "PATH": f"{root}{os.pathsep}{os.environ['PATH']}",
                "PROBE_STATE": str(state),
                "PROBE_SCENARIO": scenario,
            }
            result = subprocess.run(
                ["bash", str(SCRIPT)], env=env, text=True, capture_output=True, timeout=20, check=False
            )
            probes = json.loads(state.read_text()) if state.exists() else []
            return result, probes

    def test_unavailable_origin_is_not_reported_as_isolated(self):
        result, _ = self.run_check("unavailable")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("Refused:", result.stdout)

    def test_unhealthy_rollout_stops_before_probing(self):
        result, probes = self.run_check("unhealthy")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(probes)

    def test_allowed_paths_work_before_both_untrusted_paths_are_refused(self):
        result, probes = self.run_check("isolated")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            [probe["source"] for probe in probes], ["cloudflared", "traefik", "origin-check", "origin-check"]
        )
        self.assertTrue(all(probe["deleted"] for probe in probes))
        self.assertTrue(all("kind: Job" in probe["manifest"] for probe in probes))

    def test_reachable_origin_fails(self):
        result, probes = self.run_check("reached")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(all(probe["deleted"] for probe in probes))

    def test_one_reachable_origin_fails(self):
        result, _ = self.run_check("partial")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_connection_refused_is_not_treated_as_a_policy_drop(self):
        result, _ = self.run_check("refused")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_dns_failure_is_not_reported_as_isolated(self):
        result, _ = self.run_check("dns")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("Refused:", result.stdout)

    def test_unscheduled_probe_fails_and_is_cleaned_up(self):
        result, probes = self.run_check("pending")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(probes)
        self.assertTrue(all(probe["deleted"] for probe in probes))


if __name__ == "__main__":
    unittest.main()
