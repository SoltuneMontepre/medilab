"""Read-only preflight must identify every same-claim Pod, regardless of application labels."""

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from preflight_storage import METADATA_COMMAND, WORKSPACE_FILES, workspace_consumers, workspace_metadata


class TestPreflightStorage(unittest.TestCase):
    def test_metadata_requires_every_file_and_preserves_explicit_missing_markers(self):
        with tempfile.TemporaryDirectory() as directory:
            for count in range(4):
                with self.subTest(files=count):
                    if count:
                        path = Path(directory, WORKSPACE_FILES[count - 1])
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text("PRIVATE-CONTENT-NOT-READ")
                    output = subprocess.check_output(["/bin/bash", "-c", METADATA_COMMAND], cwd=directory, text=True)
                    result = workspace_metadata(output)
                    self.assertEqual(result["available"], count == 3)
                    self.assertEqual(len(result["file_metadata"]), 3)
                    for missing in WORKSPACE_FILES[count:]:
                        self.assertIn("missing|" + missing, result["file_metadata"])
                    self.assertNotIn("PRIVATE-CONTENT", json.dumps(result))

    def test_metadata_exec_failure_or_partial_output_cannot_claim_availability(self):
        for output in (None, "", WORKSPACE_FILES[0] + "|1|8978|8978|600\n"):
            with self.subTest(output=output):
                result = workspace_metadata(output)
                self.assertFalse(result["available"])
                self.assertEqual(len(result["file_metadata"]), 3)

    def pod(self):
        return {
            "metadata": {
                "name": "unlabelled-backup",
                "uid": "synthetic-uid",
                "ownerReferences": [{"kind": "Job", "name": "unlabelled-backup"}],
            },
            "spec": {
                "nodeName": "synthetic-node",
                "volumes": [{"name": "data", "persistentVolumeClaim": {"claimName": "cloudbeaver-workspace"}}],
                "containers": [
                    {
                        "name": "reader",
                        "env": [{"name": "DO-NOT-REPORT", "value": "SECRET-CANARY"}],
                        "volumeMounts": [{"name": "data", "mountPath": "/workspace"}],
                    }
                ],
            },
            "status": {"phase": "Running"},
        }

    def test_unlabelled_job_is_included_without_secret_content(self):
        value = workspace_consumers([self.pod()], "cloudbeaver-workspace")
        self.assertEqual(value[0]["name"], "unlabelled-backup")
        self.assertEqual(value[0]["owners"], [{"kind": "Job", "name": "unlabelled-backup"}])
        self.assertTrue(value[0]["has_writable_mount"])
        self.assertNotIn("SECRET-CANARY", json.dumps(value))
        self.assertNotIn("DO-NOT-REPORT", json.dumps(value))

    def test_other_claim_and_no_claim_are_excluded(self):
        pod = self.pod()
        pod["spec"]["volumes"][0]["persistentVolumeClaim"]["claimName"] = "other-workspace"
        other = copy.deepcopy(pod)
        other["spec"]["volumes"] = []
        self.assertEqual(workspace_consumers([pod, other], "cloudbeaver-workspace"), [])

    def test_read_only_volume_or_mount_is_reported(self):
        for location in ("volume", "mount"):
            with self.subTest(location=location):
                pod = self.pod()
                target = (
                    pod["spec"]["volumes"][0]["persistentVolumeClaim"]
                    if location == "volume"
                    else pod["spec"]["containers"][0]["volumeMounts"][0]
                )
                target["readOnly"] = True
                result = workspace_consumers([pod], "cloudbeaver-workspace")[0]
                self.assertTrue(result["mounts"][0]["read_only"])
                self.assertFalse(result["has_writable_mount"])

    def test_pending_init_and_terminating_debug_consumers_are_visible(self):
        for kind in ("initContainers", "ephemeralContainers"):
            with self.subTest(kind=kind):
                pod = self.pod()
                pod["metadata"]["deletionTimestamp"] = "synthetic-time"
                pod["spec"][kind] = pod["spec"].pop("containers")
                pod["status"]["phase"] = "Pending"
                result = workspace_consumers([pod], "cloudbeaver-workspace")[0]
                self.assertTrue(result["terminating"])
                self.assertTrue(result["has_writable_mount"])
                self.assertEqual(result["mounts"][0]["kind"], kind)
                self.assertEqual(result["phase"], "Pending")


if __name__ == "__main__":
    unittest.main()
