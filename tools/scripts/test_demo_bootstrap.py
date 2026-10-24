import json
import os
import runpy
import socket
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import demo_bootstrap
from demo_bootstrap import (
    BootstrapError,
    _assert_ports_available,
    _compose_environment,
    _fresh_config,
    _is_local_engine_endpoint,
    _labels,
    _prepare_accounting_foundation,
    check_normal_setup,
    reset,
    select,
    switch,
)


class SetCountryScriptTest(unittest.TestCase):
    def test_refuses_to_commit_when_country_write_did_not_persist(self):
        vietnam = type("Country", (), {"id": 240})()
        previous = type("Country", (), {"id": 1})()

        class Partner:
            def __init__(self):
                self.stored = previous
                self.cached = previous

            @property
            def country_id(self):
                return self.cached

            @country_id.setter
            def country_id(self, country):
                self.cached = country

            def invalidate_recordset(self, _fields):
                self.cached = self.stored

        partner = Partner()
        cursor = type(
            "Cursor", (), {"flush": lambda self: None, "commit": lambda self: None}
        )()
        company = type("Company", (), {"partner_id": partner})()
        environment = type(
            "Environment",
            (),
            {
                "cr": cursor,
                "ref": lambda self, xml_id: (
                    company if xml_id == "base.main_company" else vietnam
                ),
            },
        )()

        script = str(Path(__file__).with_name("demo_bootstrap_set_country.py"))
        with self.assertRaisesRegex(RuntimeError, "country was not set to Vietnam"):
            runpy.run_path(
                script,
                init_globals={"env": environment},
            )


class DemoBootstrapEnvironmentTest(unittest.TestCase):
    def completed_selection(self, root):
        project = "medilab-bootstrap-test-01"
        config = {
            "COMPOSE_PROJECT_NAME": project,
            **{
                key: f"{project}_{suffix}_owner"
                for key, suffix in (
                    ("MEDILAB_DB_VOLUME", "db"),
                    ("MEDILAB_GARAGE_VOLUME", "garage"),
                    ("MEDILAB_APP_VOLUME", "app"),
                    ("MEDILAB_CLOUDBEAVER_VOLUME", "cloudbeaver"),
                )
            },
        }
        marker = {
            "project": project,
            "owner": "owner",
            "status": "completed",
            "handoff_verified": True,
            "selected_project": True,
            "worktree": str(Path(__file__).resolve().parents[2]),
            "lifecycle_version": 2,
            "config": config,
        }
        marker_path = root / "marker.json"
        marker_path.write_text(json.dumps(marker), encoding="utf-8")
        return project, config, marker, marker_path

    def test_switch_archives_verified_selection_before_selecting_empty_project(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project, config, marker, marker_path = self.completed_selection(root)
            target = "medilab-bootstrap-reset-check"
            fresh_config = {"COMPOSE_PROJECT_NAME": target}
            with (
                patch("demo_bootstrap.MARKER", marker_path),
                patch("demo_bootstrap.SELECTIONS", root / "selections"),
                patch("demo_bootstrap.SWITCH_JOURNAL", root / "switch.json"),
                patch("demo_bootstrap._assert_local_engine"),
                patch("demo_bootstrap._read_compose_env", return_value=config),
                patch("demo_bootstrap._assert_owned_resources"),
                patch(
                    "demo_bootstrap._owned_volume_names",
                    return_value=tuple(
                        config[key]
                        for key in (
                            "MEDILAB_DB_VOLUME",
                            "MEDILAB_GARAGE_VOLUME",
                            "MEDILAB_APP_VOLUME",
                            "MEDILAB_CLOUDBEAVER_VOLUME",
                        )
                    ),
                ),
                patch("demo_bootstrap._assert_no_resources"),
                patch("demo_bootstrap._free_ports", return_value={}),
                patch("demo_bootstrap._fresh_config", return_value=fresh_config),
                patch("demo_bootstrap._assert_ports_available"),
                patch("demo_bootstrap._write_compose_env") as write_env,
            ):
                switch(target)
            selected = json.loads(marker_path.read_text())
            archived = json.loads((root / "selections" / f"{project}.json").read_text())
            self.assertEqual(archived, marker)
            self.assertEqual(selected["project"], target)
            self.assertEqual(selected["status"], "selected")
            write_env.assert_called_once_with(fresh_config)

    def test_switch_preserves_completed_selection_and_refuses_target_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _project, config, marker, marker_path = self.completed_selection(root)
            target = "medilab-bootstrap-reset-check"
            with (
                patch("demo_bootstrap.MARKER", marker_path),
                patch("demo_bootstrap.SELECTIONS", root / "selections"),
                patch("demo_bootstrap._assert_local_engine"),
                patch("demo_bootstrap._read_compose_env", return_value=config),
                patch("demo_bootstrap._assert_owned_resources"),
                patch(
                    "demo_bootstrap._owned_volume_names",
                    return_value=tuple(
                        config[key]
                        for key in (
                            "MEDILAB_DB_VOLUME",
                            "MEDILAB_GARAGE_VOLUME",
                            "MEDILAB_APP_VOLUME",
                            "MEDILAB_CLOUDBEAVER_VOLUME",
                        )
                    ),
                ),
                patch(
                    "demo_bootstrap._assert_no_resources",
                    side_effect=BootstrapError("already owns resources"),
                ),
                patch("demo_bootstrap._write_compose_env") as write_env,
                self.assertRaisesRegex(BootstrapError, "already owns resources"),
            ):
                switch(target)
            self.assertEqual(json.loads(marker_path.read_text()), marker)
            self.assertFalse((root / "selections").exists())
            write_env.assert_not_called()

    def test_switch_preserves_stale_archive_after_guarded_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = "medilab-bootstrap-test-01"
            target = "medilab-bootstrap-qweb-check"
            old_owner = str(uuid.uuid4())
            current_owner = str(uuid.uuid4())
            config = {
                "COMPOSE_PROJECT_NAME": project,
                **{
                    key: f"{project}_{suffix}_{current_owner[:8]}"
                    for key, suffix in (
                        ("MEDILAB_DB_VOLUME", "db"),
                        ("MEDILAB_GARAGE_VOLUME", "garage"),
                        ("MEDILAB_APP_VOLUME", "app"),
                        ("MEDILAB_CLOUDBEAVER_VOLUME", "cloudbeaver"),
                    )
                },
            }
            current = {
                "project": project,
                "owner": current_owner,
                "status": "completed",
                "handoff_verified": True,
                "selected_project": True,
                "worktree": str(Path(__file__).resolve().parents[2]),
                "lifecycle_version": 2,
                "config": config,
            }
            old = {**current, "owner": old_owner}
            marker_path = root / "marker.json"
            marker_path.write_text(json.dumps(current), encoding="utf-8")
            archive = root / "selections"
            archive.mkdir()
            old_path = archive / f"{project}.json"
            old_path.write_text(json.dumps(old), encoding="utf-8")
            with (
                patch("demo_bootstrap.MARKER", marker_path),
                patch("demo_bootstrap.SELECTIONS", archive),
                patch(
                    "demo_bootstrap.SWITCH_JOURNAL", root / "switch.json", create=True
                ),
                patch("demo_bootstrap._assert_local_engine"),
                patch("demo_bootstrap._read_compose_env", return_value=config),
                patch("demo_bootstrap._assert_owned_resources"),
                patch(
                    "demo_bootstrap._owned_volume_names",
                    return_value=tuple(
                        config[key]
                        for key in (
                            "MEDILAB_DB_VOLUME",
                            "MEDILAB_GARAGE_VOLUME",
                            "MEDILAB_APP_VOLUME",
                            "MEDILAB_CLOUDBEAVER_VOLUME",
                        )
                    ),
                ),
                patch("demo_bootstrap._assert_no_resources"),
                patch("demo_bootstrap._free_ports", return_value={}),
                patch(
                    "demo_bootstrap._fresh_config",
                    return_value={"COMPOSE_PROJECT_NAME": target},
                ),
                patch("demo_bootstrap._assert_ports_available"),
                patch("demo_bootstrap._write_compose_env"),
            ):
                switch(target)
            self.assertEqual(json.loads(old_path.read_text()), old)
            generation = archive / f"{project}.{current_owner}.json"
            self.assertEqual(json.loads(generation.read_text()), current)
            self.assertEqual(json.loads(marker_path.read_text())["project"], target)
            self.assertFalse((root / "switch.json").exists())

    def test_interrupted_switch_requires_verified_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = "medilab-bootstrap-test-01"
            target = "medilab-bootstrap-other-01"
            owner = str(uuid.uuid4())
            config = {
                "COMPOSE_PROJECT_NAME": source,
                **{
                    key: f"{source}_{suffix}_{owner[:8]}"
                    for key, suffix in (
                        ("MEDILAB_DB_VOLUME", "db"),
                        ("MEDILAB_GARAGE_VOLUME", "garage"),
                        ("MEDILAB_APP_VOLUME", "app"),
                        ("MEDILAB_CLOUDBEAVER_VOLUME", "cloudbeaver"),
                    )
                },
            }
            current = {
                "project": source,
                "owner": owner,
                "status": "completed",
                "handoff_verified": True,
                "selected_project": True,
                "worktree": str(Path(__file__).resolve().parents[2]),
                "lifecycle_version": 2,
                "config": config,
            }
            marker_path = root / "marker.json"
            marker_path.write_text(json.dumps(current), encoding="utf-8")
            journal = root / "switch.json"
            with (
                patch("demo_bootstrap.MARKER", marker_path),
                patch("demo_bootstrap.SELECTIONS", root / "selections"),
                patch("demo_bootstrap.SWITCH_JOURNAL", journal, create=True),
                patch("demo_bootstrap._assert_local_engine"),
                patch("demo_bootstrap._read_compose_env", return_value=config),
                patch("demo_bootstrap._assert_owned_resources"),
                patch(
                    "demo_bootstrap._owned_volume_names",
                    return_value=tuple(
                        config[key]
                        for key in (
                            "MEDILAB_DB_VOLUME",
                            "MEDILAB_GARAGE_VOLUME",
                            "MEDILAB_APP_VOLUME",
                            "MEDILAB_CLOUDBEAVER_VOLUME",
                        )
                    ),
                ),
                patch("demo_bootstrap._assert_no_resources"),
                patch("demo_bootstrap._free_ports", return_value={}),
                patch(
                    "demo_bootstrap._fresh_config",
                    return_value={"COMPOSE_PROJECT_NAME": target},
                ),
                patch("demo_bootstrap._assert_ports_available"),
                patch(
                    "demo_bootstrap._write_compose_env", side_effect=KeyboardInterrupt
                ),
                self.assertRaises(KeyboardInterrupt),
            ):
                switch(target)
            self.assertTrue(journal.exists())
            self.assertEqual(json.loads(marker_path.read_text())["project"], target)
            with (
                patch("demo_bootstrap.MARKER", marker_path),
                patch("demo_bootstrap.SWITCH_JOURNAL", journal, create=True),
                patch("demo_bootstrap._assert_local_engine"),
                patch("demo_bootstrap._read_compose_env", return_value=config),
                patch("demo_bootstrap._assert_owned_resources"),
                patch(
                    "demo_bootstrap._owned_volume_names",
                    return_value=tuple(
                        config[key]
                        for key in (
                            "MEDILAB_DB_VOLUME",
                            "MEDILAB_GARAGE_VOLUME",
                            "MEDILAB_APP_VOLUME",
                            "MEDILAB_CLOUDBEAVER_VOLUME",
                        )
                    ),
                ),
                patch("demo_bootstrap._assert_no_resources"),
            ):
                demo_bootstrap.recover_switch()
            self.assertEqual(json.loads(marker_path.read_text()), current)
            self.assertFalse(journal.exists())

    def test_saved_selection_uses_only_the_owner_verified_by_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            project = "medilab-bootstrap-test-01"
            archive = Path(directory)
            owners = (str(uuid.uuid4()), str(uuid.uuid4()))
            markers = []
            for owner in owners:
                config = {
                    "COMPOSE_PROJECT_NAME": project,
                    **{
                        key: f"{project}_{suffix}_{owner[:8]}"
                        for key, suffix in (
                            ("MEDILAB_DB_VOLUME", "db"),
                            ("MEDILAB_GARAGE_VOLUME", "garage"),
                            ("MEDILAB_APP_VOLUME", "app"),
                            ("MEDILAB_CLOUDBEAVER_VOLUME", "cloudbeaver"),
                        )
                    },
                }
                markers.append(
                    {
                        "project": project,
                        "owner": owner,
                        "status": "completed",
                        "handoff_verified": True,
                        "selected_project": True,
                        "worktree": str(Path(__file__).resolve().parents[2]),
                        "lifecycle_version": 2,
                        "config": config,
                    }
                )
            (archive / f"{project}.json").write_text(json.dumps(markers[0]))
            (archive / f"{project}.{owners[1]}.json").write_text(json.dumps(markers[1]))

            def inspect_owner(_project, owner):
                if owner != owners[1]:
                    raise BootstrapError("Historical owner has no resources")

            with (
                patch("demo_bootstrap.SELECTIONS", archive),
                patch(
                    "demo_bootstrap._assert_owned_resources", side_effect=inspect_owner
                ),
                patch(
                    "demo_bootstrap._owned_volume_names",
                    return_value=tuple(
                        markers[1]["config"][key]
                        for key in (
                            "MEDILAB_DB_VOLUME",
                            "MEDILAB_GARAGE_VOLUME",
                            "MEDILAB_APP_VOLUME",
                            "MEDILAB_CLOUDBEAVER_VOLUME",
                        )
                    ),
                ),
            ):
                self.assertEqual(demo_bootstrap._saved_selection(project), markers[1])

    def test_saved_selection_rejects_foreign_or_ambiguous_resources(self):
        with tempfile.TemporaryDirectory() as directory:
            project = "medilab-bootstrap-test-01"
            marker = {
                "project": project,
                "owner": str(uuid.uuid4()),
                "status": "completed",
                "handoff_verified": True,
                "selected_project": True,
                "worktree": str(Path(__file__).resolve().parents[2]),
                "lifecycle_version": 2,
                "config": {"COMPOSE_PROJECT_NAME": project},
            }
            archive = Path(directory)
            (archive / f"{project}.json").write_text(json.dumps(marker))
            with (
                patch("demo_bootstrap.SELECTIONS", archive),
                patch(
                    "demo_bootstrap._assert_owned_resources",
                    side_effect=BootstrapError("foreign owner label"),
                ),
                self.assertRaisesRegex(BootstrapError, "no unique resource-verified"),
            ):
                demo_bootstrap._saved_selection(project)

    def test_recover_switch_accepts_verified_completed_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = {
                "project": "medilab-bootstrap-first",
                "owner": str(uuid.uuid4()),
                "config": {"COMPOSE_PROJECT_NAME": "medilab-bootstrap-first"},
                "status": "completed",
            }
            target = {
                "project": "medilab-bootstrap-second",
                "owner": str(uuid.uuid4()),
                "config": {"COMPOSE_PROJECT_NAME": "medilab-bootstrap-second"},
                "status": "completed",
            }
            marker_path = root / "marker.json"
            marker_path.write_text(json.dumps(target), encoding="utf-8")
            journal = root / "switch.json"
            journal.write_text(
                json.dumps({"from": source, "to": target}), encoding="utf-8"
            )
            with (
                patch("demo_bootstrap.MARKER", marker_path),
                patch("demo_bootstrap.SWITCH_JOURNAL", journal),
                patch("demo_bootstrap._assert_local_engine"),
                patch("demo_bootstrap._verify_completed_selection") as verify,
                patch(
                    "demo_bootstrap._read_compose_env", return_value=target["config"]
                ),
            ):
                demo_bootstrap.recover_switch()
            self.assertEqual(verify.call_count, 2)
            self.assertEqual(json.loads(marker_path.read_text()), target)
            self.assertFalse(journal.exists())

    def test_recover_switch_refuses_unexpected_active_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = {
                "project": "medilab-bootstrap-first",
                "owner": str(uuid.uuid4()),
                "config": {"COMPOSE_PROJECT_NAME": "medilab-bootstrap-first"},
                "status": "completed",
            }
            target = {
                "project": "medilab-bootstrap-second",
                "owner": str(uuid.uuid4()),
                "config": {"COMPOSE_PROJECT_NAME": "medilab-bootstrap-second"},
                "status": "completed",
            }
            foreign = {**target, "owner": str(uuid.uuid4())}
            marker_path = root / "marker.json"
            marker_path.write_text(json.dumps(foreign), encoding="utf-8")
            journal = root / "switch.json"
            journal.write_text(
                json.dumps({"from": source, "to": target}), encoding="utf-8"
            )
            with (
                patch("demo_bootstrap.MARKER", marker_path),
                patch("demo_bootstrap.SWITCH_JOURNAL", journal),
                patch("demo_bootstrap._assert_local_engine"),
                patch("demo_bootstrap._verify_completed_selection"),
                patch(
                    "demo_bootstrap._read_compose_env", return_value=target["config"]
                ),
                self.assertRaisesRegex(BootstrapError, "manual review is required"),
            ):
                demo_bootstrap.recover_switch()
            self.assertTrue(journal.exists())
            self.assertEqual(json.loads(marker_path.read_text()), foreign)

    def test_switch_to_resource_verified_archived_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current_project = "medilab-bootstrap-current"
            target_project = "medilab-bootstrap-previous"

            def completed(project):
                owner = str(uuid.uuid4())
                return {
                    "project": project,
                    "owner": owner,
                    "status": "completed",
                    "handoff_verified": True,
                    "selected_project": True,
                    "worktree": str(Path(__file__).resolve().parents[2]),
                    "lifecycle_version": 2,
                    "config": {
                        "COMPOSE_PROJECT_NAME": project,
                        **{
                            key: f"{project}_{suffix}_{owner[:8]}"
                            for key, suffix in (
                                ("MEDILAB_DB_VOLUME", "db"),
                                ("MEDILAB_GARAGE_VOLUME", "garage"),
                                ("MEDILAB_APP_VOLUME", "app"),
                                ("MEDILAB_CLOUDBEAVER_VOLUME", "cloudbeaver"),
                            )
                        },
                    },
                }

            current, target = completed(current_project), completed(target_project)
            marker_path = root / "marker.json"
            marker_path.write_text(json.dumps(current), encoding="utf-8")
            archive = root / "selections"
            archive.mkdir()
            (archive / f"{target_project}.json").write_text(
                json.dumps(target), encoding="utf-8"
            )

            def volume_names(project, _owner):
                marker = current if project == current_project else target
                return tuple(
                    marker["config"][key]
                    for key in (
                        "MEDILAB_DB_VOLUME",
                        "MEDILAB_GARAGE_VOLUME",
                        "MEDILAB_APP_VOLUME",
                        "MEDILAB_CLOUDBEAVER_VOLUME",
                    )
                )

            with (
                patch("demo_bootstrap.MARKER", marker_path),
                patch("demo_bootstrap.SELECTIONS", archive),
                patch("demo_bootstrap.SWITCH_JOURNAL", root / "switch.json"),
                patch("demo_bootstrap._assert_local_engine"),
                patch(
                    "demo_bootstrap._read_compose_env", return_value=current["config"]
                ),
                patch("demo_bootstrap._assert_owned_resources"),
                patch("demo_bootstrap._owned_volume_names", side_effect=volume_names),
                patch("demo_bootstrap._write_compose_env") as write_env,
            ):
                switch(target_project)
            self.assertEqual(json.loads(marker_path.read_text()), target)
            self.assertEqual(
                json.loads((archive / f"{current_project}.json").read_text()), current
            )
            self.assertFalse((root / "switch.json").exists())
            write_env.assert_called_once_with(target["config"])

    def test_select_refuses_existing_resources_without_writing_marker(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("demo_bootstrap.MARKER", Path(temporary) / "marker.json"),
            patch("demo_bootstrap._assert_local_engine"),
            patch(
                "demo_bootstrap._assert_no_resources",
                side_effect=BootstrapError("already owns resources"),
            ),
            patch("demo_bootstrap._write_compose_env") as write_env,
        ):
            with self.assertRaisesRegex(BootstrapError, "already owns resources"):
                select("medilab-bootstrap-test-01")
            write_env.assert_not_called()

    def test_select_persists_unique_project_owner_ports_and_image(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("demo_bootstrap.MARKER", Path(temporary) / "marker.json"),
            patch("demo_bootstrap._assert_local_engine"),
            patch("demo_bootstrap._assert_no_resources"),
            patch(
                "demo_bootstrap._free_ports",
                return_value={
                    "MEDILAB_ODOO_PORT": "28069",
                    "MEDILAB_DB_PORT": "25432",
                    "MEDILAB_GARAGE_PORT": "23900",
                    "MEDILAB_GARAGE_ADMIN_PORT": "23903",
                    "MEDILAB_CLOUDBEAVER_PORT": "28978",
                },
            ),
            patch("demo_bootstrap._assert_ports_available"),
            patch("demo_bootstrap._write_compose_env") as write_env,
        ):
            select("medilab-bootstrap-test-01")
            marker = json.loads((Path(temporary) / "marker.json").read_text())

        self.assertEqual(marker["status"], "selected")
        self.assertTrue(marker["selected_project"])
        self.assertEqual(marker["project"], "medilab-bootstrap-test-01")
        self.assertEqual(marker["config"]["MEDILAB_ODOO_PORT"], "28069")
        self.assertIn(
            "medilab-bootstrap-test-01-odoo", marker["config"]["MEDILAB_ODOO_IMAGE"]
        )
        self.assertEqual(write_env.call_args.args[0], marker["config"])

    def test_interrupted_initial_selection_cannot_authorize_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            marker_path = Path(directory) / "marker.json"
            with (
                patch("demo_bootstrap.MARKER", marker_path),
                patch("demo_bootstrap._assert_local_engine"),
                patch("demo_bootstrap._assert_no_resources"),
                patch("demo_bootstrap._free_ports", return_value={}),
                patch("demo_bootstrap._assert_ports_available"),
                patch(
                    "demo_bootstrap._write_compose_env", side_effect=KeyboardInterrupt
                ),
                self.assertRaises(KeyboardInterrupt),
            ):
                select("medilab-bootstrap-interrupted")
            self.assertEqual(json.loads(marker_path.read_text())["status"], "selected")
            with (
                patch("demo_bootstrap.MARKER", marker_path),
                patch("demo_bootstrap._assert_local_engine"),
                patch("demo_bootstrap._run") as run,
                self.assertRaisesRegex(BootstrapError, "no verified fresh bootstrap"),
            ):
                reset()
            run.assert_not_called()

    def test_selecting_the_same_completed_project_preserves_its_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker_path = Path(temporary) / "marker.json"
            project = "medilab-bootstrap-test-01"
            owner = "owner-id"
            volumes = {
                key: f"{project}_{suffix}_{owner}"
                for key, suffix in (
                    ("MEDILAB_DB_VOLUME", "db"),
                    ("MEDILAB_GARAGE_VOLUME", "garage"),
                    ("MEDILAB_APP_VOLUME", "app"),
                    ("MEDILAB_CLOUDBEAVER_VOLUME", "cloudbeaver"),
                )
            }
            config = {"COMPOSE_PROJECT_NAME": project, **volumes}
            marker = {
                "project": project,
                "owner": owner,
                "status": "completed",
                "handoff_verified": True,
                "selected_project": True,
                "worktree": str(Path(__file__).resolve().parents[2]),
                "lifecycle_version": 2,
                "config": config,
            }
            marker_path.write_text(json.dumps(marker), encoding="utf-8")
            with (
                patch("demo_bootstrap.MARKER", marker_path),
                patch("demo_bootstrap._assert_local_engine"),
                patch("demo_bootstrap._assert_owned_resources"),
                patch(
                    "demo_bootstrap._owned_volume_names",
                    return_value=tuple(volumes.values()),
                ),
                patch("demo_bootstrap._read_compose_env", return_value=config),
                patch("demo_bootstrap._write_marker") as write_marker,
                patch("demo_bootstrap._write_compose_env") as write_env,
            ):
                select(project)
            self.assertEqual(json.loads(marker_path.read_text()), marker)
            write_marker.assert_not_called()
            write_env.assert_not_called()

    def test_fresh_ports_must_be_unique(self):
        ports = {
            "MEDILAB_ODOO_PORT": "18069",
            "MEDILAB_DB_PORT": "15432",
            "MEDILAB_GARAGE_PORT": "18069",
            "MEDILAB_GARAGE_ADMIN_PORT": "3903",
            "MEDILAB_CLOUDBEAVER_PORT": "8978",
        }

        with self.assertRaisesRegex(BootstrapError, "must be distinct"):
            _assert_ports_available(ports)

    def test_occupied_host_port_fails_before_creating_resources(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            occupied.bind(("0.0.0.0", 0))
            ports = {
                "MEDILAB_ODOO_PORT": str(occupied.getsockname()[1]),
                "MEDILAB_DB_PORT": "15432",
                "MEDILAB_GARAGE_PORT": "3900",
                "MEDILAB_GARAGE_ADMIN_PORT": "3903",
                "MEDILAB_CLOUDBEAVER_PORT": "8978",
            }
            with self.assertRaisesRegex(BootstrapError, "unavailable"):
                _assert_ports_available(ports)

    def test_reset_refuses_unowned_environments_before_removing_resources(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("demo_bootstrap.MARKER", Path(temporary) / "missing.json"),
            patch("demo_bootstrap.project_name", return_value="medilab-test"),
            patch("demo_bootstrap._assert_local_engine"),
            patch("demo_bootstrap._run") as run,
            self.assertRaisesRegex(BootstrapError, "no verified fresh bootstrap"),
        ):
            reset()

        run.assert_not_called()

    def test_accounting_foundation_precedes_application_install(self):
        calls = []

        with (
            patch(
                "demo_bootstrap._run_odoo",
                side_effect=lambda args, **kwargs: calls.append(("odoo", args)),
            ),
            patch(
                "demo_bootstrap._run_oneoff_shell",
                side_effect=lambda *args, **kwargs: calls.append(("shell", args)),
            ),
        ):
            _prepare_accounting_foundation("project", "owner", {})

        self.assertEqual(
            [kind for kind, _args in calls],
            ["odoo", "shell", "odoo", "shell"],
        )
        self.assertIn("base", calls[0][1])
        self.assertIn("l10n_vn", calls[2][1])

    def test_container_engine_endpoint_must_be_local(self):
        self.assertTrue(_is_local_engine_endpoint("unix:///run/podman.sock"))
        self.assertTrue(_is_local_engine_endpoint("npipe:////./pipe/docker_engine"))
        self.assertTrue(_is_local_engine_endpoint("tcp://localhost:2375"))
        self.assertFalse(_is_local_engine_endpoint("tcp://engine.example:2375"))
        self.assertFalse(_is_local_engine_endpoint("ssh://engine.example"))

    def test_network_labels_support_podman_inspect_output(self):
        labels = {"com.medilab.bootstrap.owner": "owner-id"}

        self.assertEqual(_labels({"labels": labels}, "networks"), labels)

    def test_compose_environment_uses_only_local_credentials(self):
        with patch.dict(
            os.environ,
            {
                "MEDILAB_DB_PASSWORD": "production-password",
                "GARAGE_RPC_SECRET": "production-secret",
                "MEDILAB_ODOO_PORT": "18069",
                "ODOO_DEV": "xml",
                "DOPPLER_PROJECT": "production",
            },
            clear=False,
        ):
            environment = _compose_environment("medilab-local-test", "owner-id")

        self.assertEqual(environment["MEDILAB_DB_PASSWORD"], "root")
        self.assertEqual(environment["GARAGE_RPC_SECRET"], "0" * 63 + "2")
        self.assertNotIn("DOPPLER_PROJECT", environment)
        self.assertNotIn("ODOO_DEV", environment)
        self.assertEqual(environment["MEDILAB_DEMO_BOOTSTRAP_OWNER"], "owner-id")
        self.assertEqual(environment["MEDILAB_ODOO_PORT"], "18069")

    def test_selected_ports_override_existing_worktree_ports(self):
        ports = {
            "MEDILAB_ODOO_PORT": "28069",
            "MEDILAB_DB_PORT": "25432",
            "MEDILAB_GARAGE_PORT": "23900",
            "MEDILAB_GARAGE_ADMIN_PORT": "23903",
            "MEDILAB_CLOUDBEAVER_PORT": "28978",
        }
        with patch.dict(os.environ, {"MEDILAB_ODOO_PORT": "8069"}):
            config = _fresh_config("medilab-bootstrap-test-01", "aaaaaaaa-owner", ports)
            environment = _compose_environment(
                config["COMPOSE_PROJECT_NAME"], "aaaaaaaa-owner", config
            )
        self.assertEqual(config["MEDILAB_ODOO_PORT"], "28069")
        self.assertEqual(
            environment["BUCKET_LABORATORY_PUBLIC_ADDRESS"], "http://localhost:23900"
        )

    def test_normal_setup_refuses_an_incomplete_bootstrap(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "marker.json"
            marker.write_text(
                json.dumps({"project": "medilab-test", "status": "failed"}),
                encoding="utf-8",
            )
            with (
                patch("demo_bootstrap.MARKER", marker),
                patch("demo_bootstrap.project_name", return_value="medilab-test"),
                self.assertRaises(BootstrapError),
            ):
                check_normal_setup()

    def test_normal_setup_refuses_bootstrap_resources_without_a_marker(self):
        resources = {
            "containers": [],
            "networks": [],
            "volumes": [
                {
                    "Labels": {
                        "com.medilab.bootstrap.owner": "owner-id",
                    }
                }
            ],
        }
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("demo_bootstrap.MARKER", Path(temporary) / "missing.json"),
            patch("demo_bootstrap.project_name", return_value="medilab-test"),
            patch("demo_bootstrap._resources", return_value=resources),
            self.assertRaises(BootstrapError),
        ):
            check_normal_setup()


if __name__ == "__main__":
    unittest.main()
