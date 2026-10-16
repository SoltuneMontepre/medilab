import re
from pathlib import Path

from odoo_intelligence.workspace import RELEASE

ROOT = Path(__file__).resolve().parents[3]


def pinned(path: str, pattern: str) -> str:
    return re.search(pattern, (ROOT / path).read_text(), re.MULTILINE).group(1)


def test_odoo_revision_matches_the_pyright_source():
    revision = pinned("tools/taskfiles/dev.taskfile.yml", r"^\s*ODOO_SOURCE_REVISION:\s*(\S+)")
    assert RELEASE["odoo_revision"] == revision


def test_terraform_version_matches_the_infrastructure():
    version = pinned("infra/terraform.tf", r'required_version\s*=\s*"([^"]+)"')
    assert RELEASE["terraform"]["version"] == version
