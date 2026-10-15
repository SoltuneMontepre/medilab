import pytest

from odoo_intelligence.workspace import Workspace, utf16_position


def test_navigation_cannot_escape_worktree(tmp_path):
    root = tmp_path / "checkout"
    root.mkdir()
    outside = tmp_path / "secret.py"
    outside.write_text("secret")
    (root / "link.py").symlink_to(outside)
    workspace = Workspace(root)
    for path in ["../secret.py", str(outside), "link.py"]:
        with pytest.raises(ValueError, match="worktree"):
            workspace.document(path)


def test_document_and_utf16_positions(tmp_path):
    path = tmp_path / "spaces #" / "model.py"
    path.parent.mkdir()
    text = '# 😀\nvalue = "res.partner"\n'
    path.write_text(text)
    workspace = Workspace(tmp_path)
    assert workspace.document("spaces #/model.py") == path
    assert utf16_position(text, "res.partner") == {"line": 1, "character": 9}
    assert utf16_position(text, "😀", offset=1) == {"line": 0, "character": 4}
    with pytest.raises(ValueError):
        workspace.position(path, -1, 0)
    with pytest.raises(ValueError):
        workspace.position(path, 1, 999)


def test_sessions_do_not_share_log_directories(tmp_path):
    first = Workspace(tmp_path).session_directory()
    second = Workspace(tmp_path).session_directory()
    assert first != second
    assert first.is_relative_to(tmp_path)
    assert second.is_relative_to(tmp_path)


def test_watched_addon_changes_include_create_edit_and_delete(tmp_path):
    directory = tmp_path / "src/core/modules/example"
    directory.mkdir(parents=True)
    first = directory / "models.py"
    first.write_text("first")
    workspace = Workspace(tmp_path)
    before = workspace.addon_snapshot()
    first.write_text("changed and longer")
    second = directory / "views.xml"
    second.write_text("<odoo/>")
    changes = workspace.addon_changes(before)
    assert {item["uri"]: item["type"] for item in changes} == {first.as_uri(): 2, second.as_uri(): 1}
    before = workspace.addon_snapshot()
    second.unlink()
    assert workspace.addon_changes(before) == [{"uri": second.as_uri(), "type": 3}]
