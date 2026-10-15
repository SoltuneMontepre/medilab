from pathlib import Path

import pytest

from odoo_intelligence.lsp import LspClient
from odoo_intelligence.verify import CASES
from odoo_intelligence.workspace import utf16_position


def test_unsupported_methods_are_rejected_before_server_start(tmp_path):
    client = LspClient(tmp_path)
    for method in ["textDocument/rename", "textDocument/diagnostic", "workspace/executeCommand"]:
        with pytest.raises(ValueError, match="Unsupported"):
            client.request(method, {})
    assert client.transport is None


def test_model_references_do_not_crash_on_unopened_definition():
    root = Path(__file__).resolve().parents[3]
    client = LspClient(root)
    if not client.workspace.binary.exists():
        pytest.skip("Run task ai:setup to test the official server.")
    case = next(case for case in CASES if case["name"] == "custom_model")
    position = utf16_position((root / case["path"]).read_text(), case["needle"], case["offset"])
    try:
        result = client.navigate(
            "textDocument/references",
            case["path"],
            position["line"],
            position["character"],
            context={"includeDeclaration": True},
        )
        assert any(item["uri"].endswith(case["target"]) for item in result)
    finally:
        client.close()


def test_references_do_not_open_a_package_definition(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    package = root / "package"
    package.mkdir()
    usage = root / "usage.py"
    usage.write_text("import package\n")
    reference = {"uri": usage.as_uri(), "range": {"start": {"line": 0, "character": 7}}}
    client = LspClient(root)
    opened = []
    monkeypatch.setattr(client, "start", lambda: None)
    monkeypatch.setattr(client, "refresh_addons", lambda: None)
    monkeypatch.setattr(client, "sync_document", lambda path: opened.append(path) or path.as_uri())

    def request(method, _params):
        if method == "textDocument/definition":
            return [{"targetUri": package.as_uri(), "targetSelectionRange": {"start": {"line": 0, "character": 0}}}]
        return [reference]

    monkeypatch.setattr(client, "request", request)
    assert client.navigate("textDocument/references", "usage.py", 0, 7) == [reference]
    assert opened == [usage]


def test_delayed_diagnostics_for_an_old_version_are_stale(tmp_path, monkeypatch):
    import time

    path = tmp_path / "model.py"
    path.write_text("name = 1")
    client = LspClient(tmp_path)
    client.documents[path.as_uri()] = {"text": "name = 1", "version": 2, "sent_at": time.time() - 1}
    client._notification(
        "textDocument/publishDiagnostics",
        {
            "uri": path.as_uri(),
            "version": 1,
            "diagnostics": [],
        },
    )
    monkeypatch.setattr(client, "start", lambda: None)
    monkeypatch.setattr(client, "request", lambda *_: [])
    result = client.published_diagnostics("model.py")
    assert result["status"] == "stale"
    assert result["version"] == 1
    assert result["document_version"] == 2
