"""Operator input containment and exclusive recovery evidence, including path replacement races."""

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from operator_files import (
    new_evidence_directory,
    new_evidence_file,
    parent_directory,
    read_input,
    trusted_roots,
)


class TestOperatorFiles(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.roots = (self.root,)
        self.source = self.root / "secret"
        self.source.write_bytes(b"private input")
        self.source.chmod(0o600)

    def test_explicit_root_policy_and_private_regular_input(self):
        with patch.dict(os.environ, {"OPERATOR_ROOTS": str(self.root)}):
            self.assertEqual(trusted_roots("OPERATOR_ROOTS"), self.roots)
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            trusted_roots("OPERATOR_ROOTS")
        for value in ("/", "relative"):
            with (
                patch.dict(os.environ, {"OPERATOR_ROOTS": value}),
                self.assertRaises(ValueError),
            ):
                trusted_roots("OPERATOR_ROOTS")
        self.assertEqual(read_input(self.source, self.roots, 64, private=True), b"private input")
        with self.assertRaises(ValueError):
            read_input(self.source, self.roots, 2)
        self.source.chmod(0o644)
        with self.assertRaises(ValueError):
            read_input(self.source, self.roots, 64, private=True)
        self.assertEqual(read_input(self.source, self.roots, 64), b"private input")
        self.source.chmod(0o666)
        with self.assertRaises(ValueError):
            read_input(self.source, self.roots, 64)

    def test_outside_traversal_symlink_and_special_files_are_refused(self):
        link = self.root / "link"
        link.symlink_to(self.source)
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        for value in (
            self.root.parent / "outside",
            self.root / ".." / self.root.name / "secret",
            link,
            fifo,
            self.root,
        ):
            with self.subTest(value=value), self.assertRaises((ValueError, OSError)):
                read_input(value, self.roots, 64)
        directory = self.root / "child"
        directory.mkdir(mode=0o777)
        directory.chmod(0o777)
        (directory / "input").write_bytes(b"untrusted")
        with self.assertRaises(ValueError):
            read_input(directory / "input", self.roots, 64)
        root_link = self.root / "root-link"
        root_link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            read_input(root_link / "secret", (root_link,), 64)

    def test_new_evidence_is_private_and_never_overwrites(self):
        output = self.root / "incident"
        with new_evidence_directory(output, self.roots) as descriptor:
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
            with new_evidence_file(descriptor, "evidence.json") as stream:
                stream.write(b"retained")
            self.assertEqual(stat.S_IMODE((output / "evidence.json").stat().st_mode), 0o600)
            with (
                self.assertRaises(FileExistsError),
                new_evidence_file(descriptor, "evidence.json"),
            ):
                self.fail("Existing evidence must never open for writing")
            (output / "document.bin").symlink_to(self.source)
            with (
                self.assertRaises(FileExistsError),
                new_evidence_file(descriptor, "document.bin"),
            ):
                self.fail("An existing link must never open for writing")
            with (
                self.assertRaises(ValueError),
                new_evidence_file(descriptor, "../secret"),
            ):
                self.fail("Only fixed evidence names are accepted")
        self.assertEqual(self.source.read_bytes(), b"private input")
        self.assertEqual((output / "evidence.json").read_bytes(), b"retained")
        with (
            self.assertRaises(FileExistsError),
            new_evidence_directory(output, self.roots),
        ):
            self.fail("Existing incident directories are retained")

    def test_pinned_parent_survives_directory_replacement(self):
        parent = self.root / "parent"
        parent.mkdir()
        replacement = self.root / "replacement"
        replacement.mkdir()
        original = self.root / "original"
        with parent_directory(parent / "evidence.json", self.roots) as (
            descriptor,
            name,
        ):
            parent.rename(original)
            parent.symlink_to(replacement, target_is_directory=True)
            with new_evidence_file(descriptor, name) as stream:
                stream.write(b"pinned")
        self.assertEqual((original / "evidence.json").read_bytes(), b"pinned")
        self.assertFalse((replacement / "evidence.json").exists())
