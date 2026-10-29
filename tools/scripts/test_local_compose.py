import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import onlyoffice
from demo_bootstrap import BootstrapError
from local_compose import (
    _resolve,
    guard_demo_install,
    guard_e2e_app,
    guard_uninstall,
    main,
)
from onlyoffice_state import OnlyofficeError


class LocalComposeTest(unittest.TestCase):
    def test_compose_wrapper_rejects_volume_deletion(self):
        for flag in ("-v", "--volumes"):
            with (
                self.subTest(flag=flag),
                patch("local_compose.sys.argv", ["local_compose.py", "down", flag]),
                patch(
                    "local_compose._resolve", return_value=("owned", None, [], {})
                ) as resolve,
                patch(
                    "local_compose.subprocess.run",
                    return_value=type("Result", (), {"returncode": 0})(),
                ) as run,
                self.assertRaises(SystemExit) as result,
            ):
                main()
            self.assertEqual(result.exception.code, 1)
            resolve.assert_not_called()
            run.assert_not_called()

    def test_compose_wrapper_rejects_project_override(self):
        with (
            patch(
                "local_compose.sys.argv",
                ["local_compose.py", "--project-name", "foreign", "up"],
            ),
            patch(
                "local_compose._resolve", return_value=("owned", None, [], {})
            ) as resolve,
            patch(
                "local_compose.subprocess.run",
                return_value=type("Result", (), {"returncode": 0})(),
            ) as run,
            self.assertRaises(SystemExit) as result,
        ):
            main()
        self.assertEqual(result.exception.code, 1)
        resolve.assert_not_called()
        run.assert_not_called()

    def test_managed_down_drains_before_compose_and_holds_operation_lock(self):
        events = []

        @contextmanager
        def drain(*_args):
            events.append("drained")
            yield
            events.append("unlocked")

        def compose(*_args, **_kwargs):
            events.append("compose-down")
            return type("Result", (), {"returncode": 0})()

        with (
            patch("local_compose.sys.argv", ["local_compose.py", "down"]),
            patch("local_compose._resolve", return_value=("owned", None, [], {})),
            patch(
                "local_compose.resolve_addon", return_value=(["-f", "addon.yml"], {})
            ),
            patch.object(onlyoffice, "drained_for_compose", drain, create=True),
            patch("local_compose.subprocess.run", side_effect=compose),
            self.assertRaises(SystemExit) as result,
        ):
            main()
        self.assertEqual(result.exception.code, 0)
        self.assertEqual(events, ["drained", "compose-down", "unlocked"])

    def test_managed_drain_failure_prevents_compose_from_stopping_base(self):
        with (
            patch("local_compose.sys.argv", ["local_compose.py", "down"]),
            patch("local_compose._resolve", return_value=("owned", None, [], {})),
            patch(
                "local_compose.resolve_addon", return_value=(["-f", "addon.yml"], {})
            ),
            patch.object(
                onlyoffice,
                "drained_for_compose",
                side_effect=OnlyofficeError("drain refused"),
                create=True,
            ),
            patch("local_compose.subprocess.run") as run,
            self.assertRaises(SystemExit) as result,
        ):
            main()
        self.assertEqual(result.exception.code, 1)
        run.assert_not_called()

    def test_base_only_down_does_not_require_editor_private_state(self):
        with (
            patch("local_compose.sys.argv", ["local_compose.py", "down"]),
            patch("local_compose._resolve", return_value=("owned", None, [], {})),
            patch("local_compose.resolve_addon", return_value=([], {})),
            patch.object(onlyoffice, "drained_for_compose", create=True) as drain,
            patch(
                "local_compose.subprocess.run",
                return_value=type("Result", (), {"returncode": 0})(),
            ) as run,
            self.assertRaises(SystemExit) as result,
        ):
            main()
        self.assertEqual(result.exception.code, 0)
        drain.assert_not_called()
        run.assert_called_once()

    def test_completed_bootstrap_uses_owned_compose_configuration(self):
        config = {
            "COMPOSE_PROJECT_NAME": "medilab-test",
            "MEDILAB_DEMO_BOOTSTRAP_OWNER": "owner",
            "MEDILAB_DB_VOLUME": "medilab-test-db-owner",
            "MEDILAB_GARAGE_VOLUME": "medilab-test-garage-owner",
            "MEDILAB_APP_VOLUME": "medilab-test-app-owner",
            "MEDILAB_CLOUDBEAVER_VOLUME": "medilab-test-cloudbeaver-owner",
        }
        marker = {
            "config": config,
            "handoff_verified": True,
            "lifecycle_version": 2,
            "owner": "owner",
            "project": "medilab-test",
            "status": "completed",
        }
        resources = {"containers": [], "networks": [], "volumes": []}
        with (
            patch("local_compose.project_name", return_value="medilab-test"),
            patch("local_compose._read_marker", return_value=marker),
            patch("local_compose._read_compose_env", return_value=config),
            patch("local_compose._assert_owned_resources", return_value=resources),
            patch(
                "local_compose._owned_volume_names",
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
        ):
            project, resolved, files, env = _resolve("up")

        self.assertEqual(project, "medilab-test")
        self.assertIs(resolved, marker)
        self.assertIn("docker-compose.owned.yml", " ".join(files))
        self.assertEqual(env["MEDILAB_DB_VOLUME"], config["MEDILAB_DB_VOLUME"])

    def test_completed_bootstrap_allows_explicit_xml_development_mode(self):
        config = {
            "COMPOSE_PROJECT_NAME": "medilab-test",
            "MEDILAB_DB_VOLUME": "db-volume",
            "MEDILAB_GARAGE_VOLUME": "garage-volume",
            "MEDILAB_APP_VOLUME": "app-volume",
            "MEDILAB_CLOUDBEAVER_VOLUME": "cloudbeaver-volume",
        }
        marker = {
            "config": config,
            "lifecycle_version": 2,
            "owner": "owner",
            "project": "medilab-test",
            "status": "completed",
        }
        with (
            patch.dict(os.environ, {"ODOO_DEV": "xml"}),
            patch("local_compose.project_name", return_value="medilab-test"),
            patch("local_compose._read_marker", return_value=marker),
            patch("local_compose._read_compose_env", return_value=config),
            patch("local_compose._assert_owned_resources"),
            patch(
                "local_compose._owned_volume_names",
                return_value=(
                    "db-volume",
                    "garage-volume",
                    "app-volume",
                    "cloudbeaver-volume",
                ),
            ),
        ):
            _project, _marker, _files, environment = _resolve("up")
        self.assertEqual(environment["ODOO_DEV"], "xml")

    def test_completed_bootstrap_with_missing_volumes_points_to_reset(self):
        config = {
            "COMPOSE_PROJECT_NAME": "medilab-test",
            "MEDILAB_DB_VOLUME": "db-volume",
            "MEDILAB_GARAGE_VOLUME": "garage-volume",
            "MEDILAB_APP_VOLUME": "app-volume",
            "MEDILAB_CLOUDBEAVER_VOLUME": "cloudbeaver-volume",
        }
        marker = {
            "config": config,
            "lifecycle_version": 2,
            "owner": "owner",
            "project": "medilab-test",
            "status": "completed",
        }
        with (
            patch("local_compose.project_name", return_value="medilab-test"),
            patch("local_compose._read_marker", return_value=marker),
            patch("local_compose._read_compose_env", return_value=config),
            patch("local_compose._assert_owned_resources"),
            patch("local_compose._owned_volume_names", return_value=("app-volume",)),
            self.assertRaisesRegex(
                BootstrapError,
                r"cloudbeaver-volume, db-volume, garage-volume .*`task reset`",
            ),
        ):
            _resolve("up")

    def test_incomplete_bootstrap_blocks_normal_start(self):
        marker = {
            "config": {},
            "lifecycle_version": 2,
            "owner": "owner",
            "project": "medilab-test",
            "status": "handoff",
        }
        with (
            patch("local_compose.project_name", return_value="medilab-test"),
            patch("local_compose._read_marker", return_value=marker),
            self.assertRaisesRegex(
                BootstrapError, "normal Compose operations are blocked"
            ),
        ):
            _resolve("up")

    def test_upgrade_refuses_to_install_uninstalled_demo_module(self):
        with (
            patch(
                "local_compose._resolve", return_value=("medilab-test", None, [], {})
            ),
            patch(
                "local_compose.subprocess.run",
                return_value=type(
                    "Result", (), {"returncode": 0, "stdout": "uninstalled"}
                )(),
            ),
            self.assertRaisesRegex(BootstrapError, "Refusing to install sol_demo"),
        ):
            guard_demo_install("sol_laboratory,sol_demo")

    def test_upgrade_allows_installed_demo_module(self):
        with (
            patch(
                "local_compose._resolve", return_value=("medilab-test", None, [], {})
            ),
            patch(
                "local_compose.subprocess.run",
                return_value=type(
                    "Result", (), {"returncode": 0, "stdout": "installed"}
                )(),
            ),
        ):
            guard_demo_install("sol_demo")

    def test_e2e_app_refuses_to_reinstall_an_owned_demo_database(self):
        with (
            patch(
                "local_compose._resolve",
                return_value=("medilab-test", {"status": "completed"}, [], {}),
            ),
            self.assertRaisesRegex(BootstrapError, "fresh demo database"),
        ):
            guard_e2e_app()

    def test_e2e_app_keeps_legacy_test_database_setup(self):
        with patch(
            "local_compose._resolve", return_value=("medilab-test", None, [], {})
        ):
            guard_e2e_app()

    def test_uninstall_refuses_fresh_demo_filestore(self):
        with (
            patch(
                "local_compose._resolve",
                return_value=("medilab-test", {"status": "completed"}, [], {}),
            ),
            self.assertRaisesRegex(BootstrapError, "fresh demo filestore"),
        ):
            guard_uninstall()


if __name__ == "__main__":
    unittest.main()
