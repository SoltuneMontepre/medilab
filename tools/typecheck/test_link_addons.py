"""link_addons.py replaces and removes only the links it made, and never changes the folders it links to."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import link_addons
from link_addons import RECORD, LinkError

ODOO_ADDONS = ["web"]


def snapshot(*folders):
    """The links and the contents of every file under folders."""
    found = {}
    for folder in folders:
        for path in sorted(folder.rglob("*")):
            if link_addons.is_link(path):
                found[path] = ("link", os.readlink(path))
            elif path.is_file():
                found[path] = path.read_bytes()
    return found


class TestLinkAddons(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.source = self.root / "odoo-source"
        self.addons = self.source / "odoo" / "addons"
        self.write(self.addons / "base" / "__init__.py", "")
        self.write(self.source / "addons" / "web" / "__init__.py", "")
        self.write(self.source / "addons" / "web" / "static" / "app.js", "app()\n")
        self.modules = self.root / "modules"
        self.add_module(self.modules, "sol_a")
        self.add_module(self.modules, "sol_b")
        (self.modules / "notes").mkdir()

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def add_module(self, folder, name):
        self.write(folder / name / "__manifest__.py", f"{{'name': '{name}'}}\n")

    def link(self, modules=None, confirm=lambda folder: False):
        """Run the linking, declining to replace folders unless confirm says so. The linked folders hold the same files afterwards."""
        modules = modules or self.modules
        linked = (modules, self.source / "addons", self.addons / "base")
        before = snapshot(*linked)
        try:
            link_addons.link_addons(self.source, modules, ODOO_ADDONS, confirm)
        finally:
            self.assertEqual(
                snapshot(*linked), before, "linking changed a linked folder"
            )

    def assert_linked(self, name, target):
        link = self.addons / name
        self.assertTrue(link_addons.is_link(link), f"{link} is not a link")
        self.assertTrue(link.samefile(target))

    def record(self):
        return json.loads((self.source / RECORD).read_text(encoding="utf-8"))

    def test_each_odoo_addon_and_module_is_linked_and_recorded(self):
        self.link()
        self.assert_linked("web", self.source / "addons" / "web")
        self.assert_linked("sol_a", self.modules / "sol_a")
        self.assert_linked("sol_b", self.modules / "sol_b")
        self.assertFalse((self.addons / "notes").exists())
        self.assertEqual(set(self.record()), {"web", "sol_a", "sol_b"})
        self.assertTrue((self.addons / "base" / "__init__.py").is_file())

    def test_running_again_changes_nothing(self):
        self.link()
        before = {
            path.name: path.lstat()
            for path in [*self.addons.iterdir(), self.source / RECORD]
        }
        self.link()
        after = {
            path.name: path.lstat()
            for path in [*self.addons.iterdir(), self.source / RECORD]
        }
        self.assertEqual(after.keys(), before.keys())
        for name, stat in before.items():
            with self.subTest(name=name):
                self.assertEqual(
                    (after[name].st_ino, after[name].st_mtime_ns),
                    (stat.st_ino, stat.st_mtime_ns),
                )

    def test_a_link_to_a_moved_module_is_repaired(self):
        self.link()
        moved = self.root / "moved"
        self.add_module(moved, "sol_a")
        self.add_module(moved, "sol_b")
        self.link(moved)
        self.assert_linked("sol_a", moved / "sol_a")
        self.assert_linked("sol_b", moved / "sol_b")

    def test_a_broken_link_is_repaired(self):
        self.link()
        moved = self.root / "moved"
        self.modules.rename(moved)
        self.assertFalse((self.addons / "sol_a").exists())
        self.link(moved)
        self.assert_linked("sol_a", moved / "sol_a")

    def test_the_link_of_a_removed_module_is_removed(self):
        self.link()
        shutil.rmtree(self.modules / "sol_b")
        self.link()
        self.assertFalse(link_addons.is_link(self.addons / "sol_b"))
        self.assertEqual(set(self.record()), {"web", "sol_a"})

    def test_a_new_module_is_linked(self):
        self.link()
        self.add_module(self.modules, "sol_c")
        self.link()
        self.assert_linked("sol_c", self.modules / "sol_c")

    def test_a_module_change_shows_through_its_link(self):
        self.link()
        self.write(self.modules / "sol_a" / "models.py", "NAME = 1\n")
        self.assertEqual(
            (self.addons / "sol_a" / "models.py").read_text(encoding="utf-8"),
            "NAME = 1\n",
        )

    def test_other_links_are_kept(self):
        elsewhere = self.root / "elsewhere"
        self.write(elsewhere / "hr" / "__init__.py", "")
        link_addons.create_link(self.addons / "hr", elsewhere / "hr")
        link_addons.create_link(self.addons / "gone", self.modules / "gone")
        link_addons.create_link(self.addons / "sol_old", self.modules / "sol_old")
        target = os.readlink(self.addons / "hr")
        self.link()
        self.link()
        self.assertEqual(os.readlink(self.addons / "hr"), target)
        self.assertTrue(link_addons.is_link(self.addons / "gone"))
        self.assertTrue(link_addons.is_link(self.addons / "sol_old"))
        self.assertNotIn("hr", self.record())

    def test_a_link_replaced_by_someone_else_is_kept(self):
        self.link()
        elsewhere = self.root / "elsewhere"
        self.write(elsewhere / "sol_b" / "__init__.py", "")
        link_addons.remove_link(self.addons / "sol_b")
        link_addons.create_link(self.addons / "sol_b", elsewhere / "sol_b")
        target = os.readlink(self.addons / "sol_b")
        shutil.rmtree(self.modules / "sol_b")
        self.link()
        self.assertEqual(os.readlink(self.addons / "sol_b"), target)
        self.assertNotIn("sol_b", self.record())

    def test_another_link_under_a_module_name_is_kept_and_reported(self):
        elsewhere = self.root / "elsewhere"
        self.write(elsewhere / "sol_a" / "__init__.py", "")
        link_addons.create_link(self.addons / "sol_a", elsewhere / "sol_a")
        target = os.readlink(self.addons / "sol_a")
        with self.assertRaisesRegex(LinkError, "was not made by this script"):
            self.link()
        self.assertEqual(os.readlink(self.addons / "sol_a"), target)

    def test_a_folder_under_a_module_name_is_kept_when_replacing_it_is_declined(self):
        self.write(self.addons / "sol_a" / "work.py", "KEEP = 1\n")
        with self.assertRaisesRegex(LinkError, "is a folder, not a link"):
            self.link()
        self.assertEqual(
            (self.addons / "sol_a" / "work.py").read_text(encoding="utf-8"),
            "KEEP = 1\n",
        )
        self.assertFalse((self.addons / "sol_a").is_symlink())

    def test_a_folder_is_replaced_by_a_link_after_confirmation(self):
        self.write(self.addons / "sol_a" / "work.py", "OLD = 1\n")
        asked = []
        self.link(confirm=lambda folder: asked.append(folder.name) or True)
        self.assertEqual(asked, ["sol_a"])
        self.assert_linked("sol_a", self.modules / "sol_a")
        self.assertIn("sol_a", self.record())
        self.assertTrue((self.modules / "sol_a" / "__manifest__.py").is_file())

    def test_a_folder_is_declined_without_a_terminal(self):
        with mock.patch.object(link_addons.sys.stdin, "isatty", return_value=False):
            self.assertFalse(link_addons.ask_to_replace(self.addons / "sol_a"))

    def test_a_folder_is_declined_when_the_input_is_empty(self):
        with (
            mock.patch.object(link_addons.sys.stdin, "isatty", return_value=True),
            mock.patch("builtins.input", side_effect=EOFError),
        ):
            self.assertFalse(link_addons.ask_to_replace(self.addons / "sol_a"))

    def test_an_identical_odoo_addon_directory_is_kept_and_reported(self):
        shutil.copytree(self.source / "addons" / "web", self.addons / "web")
        before = snapshot(self.addons / "web")
        with self.assertRaises(LinkError):
            self.link()
        self.assertFalse(link_addons.is_link(self.addons / "web"))
        self.assertEqual(snapshot(self.addons / "web"), before)

    def test_a_matching_unmanaged_link_is_not_adopted_or_removed(self):
        link_addons.create_link(self.addons / "sol_b", self.modules / "sol_b")
        self.link()
        self.assertNotIn("sol_b", self.record())
        shutil.rmtree(self.modules / "sol_b")
        self.link()
        self.assertTrue(link_addons.is_link(self.addons / "sol_b"))

    def test_a_record_cannot_remove_a_link_outside_the_addons_folder(self):
        outside = self.source / "odoo" / "outside"
        link_addons.create_link(outside, self.modules / "sol_a")
        (self.source / RECORD).write_text(
            json.dumps({"../outside": os.readlink(outside)}), encoding="utf-8"
        )
        with self.assertRaises(LinkError):
            self.link()
        self.assertTrue(link_addons.is_link(outside))

    def test_invalid_record_names_are_rejected_before_any_links_are_created(self):
        for name in (
            "/outside",
            "..\\outside",
            "C:outside",
            ".",
            "..",
            "",
            ".. ",
            "...",
        ):
            with self.subTest(name=name):
                (self.source / RECORD).write_text(
                    json.dumps({name: "target"}), encoding="utf-8"
                )
                with self.assertRaises(LinkError):
                    self.link()
                self.assertEqual(
                    [path.name for path in self.addons.iterdir()], ["base"]
                )

    def test_a_recorded_link_replaced_by_a_directory_is_kept(self):
        self.link()
        link_addons.remove_link(self.addons / "sol_b")
        self.write(self.addons / "sol_b" / "mine.txt", "keep\n")
        shutil.rmtree(self.modules / "sol_b")
        self.link()
        self.assertEqual(
            (self.addons / "sol_b" / "mine.txt").read_text(encoding="utf-8"), "keep\n"
        )

    def test_remove_link_refuses_a_real_directory(self):
        folder = self.root / "unmanaged"
        folder.mkdir()
        with self.assertRaises(LinkError):
            link_addons.remove_link(folder)
        self.assertTrue(folder.is_dir())

    def test_a_changed_copy_of_an_odoo_addon_is_kept_and_reported(self):
        shutil.copytree(self.source / "addons" / "web", self.addons / "web")
        self.write(self.addons / "web" / "static" / "app.js", "changed()\n")
        with self.assertRaisesRegex(LinkError, "is a folder, not a link"):
            self.link()
        self.assertEqual(
            (self.addons / "web" / "static" / "app.js").read_text(encoding="utf-8"),
            "changed()\n",
        )

    def test_a_copy_with_an_extra_file_is_kept_and_reported(self):
        shutil.copytree(self.source / "addons" / "web", self.addons / "web")
        self.write(self.addons / "web" / "notes.txt", "mine\n")
        with self.assertRaises(LinkError):
            self.link()
        self.assertTrue((self.addons / "web" / "notes.txt").is_file())

    def test_a_missing_odoo_addon_changes_nothing(self):
        with self.assertRaisesRegex(LinkError, "not found"):
            link_addons.link_addons(self.source, self.modules, ["portal"])
        self.assertEqual([path.name for path in self.addons.iterdir()], ["base"])

    def test_an_unreadable_record_is_reported(self):
        (self.source / RECORD).write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(LinkError, "Delete it and run again"):
            self.link()


class TestWindowsJunctions(unittest.TestCase):
    """Platform-specific junction calls and target preservation."""

    def test_a_junction_is_made_with_mklink(self):
        done = subprocess.CompletedProcess([], 0, "Junction created\n", "")
        with (
            mock.patch.object(link_addons, "WINDOWS", True),
            mock.patch.object(link_addons.subprocess, "run", return_value=done) as run,
        ):
            link_addons.create_link(
                Path("C:/odoo/addons/sol_a"), Path("C:/medilab/modules/sol_a")
            )
        command = run.call_args.args[0]
        self.assertEqual(command[:4], ["cmd", "/c", "mklink", "/J"])
        self.assertEqual(
            [Path(part) for part in command[4:]],
            [Path("C:/odoo/addons/sol_a"), Path("C:/medilab/modules/sol_a")],
        )

    def test_a_failed_junction_is_reported(self):
        failed = subprocess.CompletedProcess(
            [], 1, "", "Cannot create a file when that file already exists.\n"
        )
        with (
            mock.patch.object(link_addons, "WINDOWS", True),
            mock.patch.object(link_addons.subprocess, "run", return_value=failed),
            self.assertRaisesRegex(LinkError, "already exists"),
        ):
            link_addons.create_link(
                Path("C:/odoo/addons/sol_a"), Path("C:/medilab/modules/sol_a")
            )

    def test_a_junction_counts_as_a_link(self):
        junction = mock.Mock(spec=Path)
        junction.is_symlink.return_value = False
        junction.is_junction.return_value = True
        self.assertTrue(link_addons.is_link(junction))

    def test_a_junction_is_removed_as_a_directory_entry(self):
        junction = mock.Mock(spec=Path)
        junction.is_junction.return_value = True
        with mock.patch.object(link_addons.os, "rmdir") as rmdir:
            link_addons.remove_link(junction)
        rmdir.assert_called_once_with(junction)
        junction.unlink.assert_not_called()

    def test_a_symbolic_link_is_removed_without_its_target(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder, "sol_a")
            target.mkdir()
            Path(target, "__manifest__.py").write_text("{}\n", encoding="utf-8")
            link = Path(folder, "link")
            link.symlink_to(target, target_is_directory=True)
            link_addons.remove_link(link)
            self.assertFalse(link.is_symlink())
            self.assertTrue(Path(target, "__manifest__.py").is_file())

    @unittest.skipUnless(os.name == "nt", "requires Windows junctions")
    def test_native_junction_cleanup_preserves_targets_and_unmanaged_junctions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "target"
            target.mkdir()
            keep = target / "keep.txt"
            keep.write_text("keep\n", encoding="utf-8")
            addons = root / "addons"
            addons.mkdir()
            links = link_addons.Links(addons, root / RECORD)
            links.place("owned", target)
            link_addons.create_link(addons / "unmanaged", target)
            self.assertTrue((addons / "owned").is_junction())
            links.remove_others([])
            self.assertFalse((addons / "owned").is_junction())
            self.assertTrue((addons / "unmanaged").is_junction())
            self.assertEqual(keep.read_text(encoding="utf-8"), "keep\n")
            link_addons.remove_link(addons / "unmanaged")


if __name__ == "__main__":
    unittest.main()
