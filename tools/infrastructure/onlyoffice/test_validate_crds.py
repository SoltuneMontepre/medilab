"""Pinned schema validation accepts trusted regular inputs and refuses unsafe CLI paths."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().with_name("validate_crds.py")
CRD = """kind: CustomResourceDefinition
spec:
  group: fixture.medilab
  names: {kind: Fixture}
  versions:
    - name: v1
      schema:
        openAPIV3Schema:
          type: object
          required: [spec]
          properties:
            spec: {type: object, required: [enabled], properties: {enabled: {type: boolean}}}
"""
MANIFEST = "apiVersion: fixture.medilab/v1\nkind: Fixture\nspec: {enabled: true}\n"


class TestValidateCrds(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.crd, self.manifest = self.root / "pinned.yaml", self.root / "manifest.yaml"
        self.crd.write_text(CRD)
        self.manifest.write_text(MANIFEST)

    def execute(self, crd=None, manifest=None, root=None):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--crd",
                str(crd or self.crd),
                str(manifest or self.manifest),
            ],
            env=dict(os.environ, MEDILAB_ONLYOFFICE_SCHEMA_ROOTS=str(root or self.root)),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def test_trusted_schema_and_manifest_are_validated(self):
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Validated 1 custom resources", result.stdout)
        self.manifest.write_text(MANIFEST.replace("true", "not-a-boolean"))
        result = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("not-a-boolean", result.stderr)

    def test_both_inputs_reject_links_traversal_and_untrusted_roots(self):
        link = self.root / "link"
        link.symlink_to(self.crd)
        for kwargs in (
            {"crd": link},
            {"manifest": link},
            {"root": self.root / "different"},
            {"crd": self.root / ".." / self.root.name / "pinned.yaml"},
        ):
            with self.subTest(kwargs=kwargs):
                self.assertNotEqual(self.execute(**kwargs).returncode, 0)
        self.manifest.chmod(0o666)
        self.assertNotEqual(self.execute().returncode, 0)
