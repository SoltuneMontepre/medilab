import hashlib
import io
import zipfile

import pytest

from odoo_intelligence.install import unpack_verified


def archive(contents):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as output:
        for name, data in contents.items():
            output.writestr(name, data)
    return stream.getvalue()


def test_bad_digest_does_not_replace_installed_release(tmp_path):
    destination = tmp_path / "release"
    destination.mkdir()
    (destination / "server").write_text("working")
    download = tmp_path / "release.zip"
    download.write_bytes(archive({"server": "replacement"}))
    with pytest.raises(ValueError, match="SHA-256"):
        unpack_verified(download, destination, "0" * 64)
    assert (destination / "server").read_text() == "working"


def test_archive_paths_cannot_escape_installation(tmp_path):
    download = tmp_path / "release.zip"
    download.write_bytes(archive({"../escaped": "bad"}))
    digest = hashlib.sha256(download.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="archive"):
        unpack_verified(download, tmp_path / "release", digest)
    assert not (tmp_path / "escaped").exists()


def test_verified_archive_is_published_with_contents(tmp_path):
    download = tmp_path / "release.zip"
    download.write_bytes(archive({"stdlib/builtins.pyi": "class object: ..."}))
    digest = hashlib.sha256(download.read_bytes()).hexdigest()
    unpack_verified(download, tmp_path / "release", digest)
    assert (tmp_path / "release/stdlib/builtins.pyi").read_text() == "class object: ..."


def test_install_can_leave_its_success_message_to_the_task_logger(tmp_path, monkeypatch, capsys):
    import odoo_intelligence.install as installer

    monkeypatch.setattr(installer, "install_release", lambda workspace: None)
    monkeypatch.setattr(installer, "install_source", lambda workspace: None)
    monkeypatch.setattr("odoo_intelligence.prerequisites.install_terraform", lambda workspace: None)

    installer.install(tmp_path, report_status=False)

    assert capsys.readouterr().out == ""


def test_install_reports_success_by_default(tmp_path, monkeypatch, capsys):
    import odoo_intelligence.install as installer
    from odoo_intelligence.workspace import RELEASE

    monkeypatch.setattr(installer, "install_release", lambda workspace: None)
    monkeypatch.setattr(installer, "install_source", lambda workspace: None)
    monkeypatch.setattr("odoo_intelligence.prerequisites.install_terraform", lambda workspace: None)

    installer.install(tmp_path)

    assert capsys.readouterr().out == (
        f"OdooLS {RELEASE['version']} and Odoo source ready in {tmp_path / '.local' / 'odoo-intelligence'}.\n"
    )


def test_install_cli_can_suppress_only_its_success_status(tmp_path, monkeypatch):
    import sys
    from unittest.mock import patch

    from odoo_intelligence import cli

    monkeypatch.setattr(sys, "argv", ["medilab-odoo", "install", "--root", str(tmp_path), "--quiet-status"])
    with patch("odoo_intelligence.install.install") as install:
        cli.main()

    install.assert_called_once_with(tmp_path, report_status=False)


def test_an_existing_mirror_must_contain_all_tracked_addons(tmp_path, monkeypatch):
    import subprocess

    from odoo_intelligence.install import install_source
    from odoo_intelligence.workspace import RELEASE, Workspace

    workspace = Workspace(tmp_path)
    workspace.source.mkdir(parents=True)
    for addon in ["account", "sale"]:
        manifest = workspace.source / "addons" / addon / "__manifest__.py"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("{}")
    subprocess.run(["git", "init", "--quiet", str(workspace.source)], check=True)
    subprocess.run(["git", "-C", str(workspace.source), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(workspace.source),
            "-c",
            "user.name=Source test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "[test] Add addon fixture",
        ],
        check=True,
    )
    revision = subprocess.check_output(["git", "-C", str(workspace.source), "rev-parse", "HEAD"], text=True).strip()
    monkeypatch.setitem(RELEASE, "odoo_revision", revision)
    (workspace.source / "addons/sale/__manifest__.py").unlink()
    with pytest.raises(RuntimeError, match="mirror"):
        install_source(workspace)
