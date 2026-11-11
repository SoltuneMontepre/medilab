"""Load the pure callback services without installing Odoo or executing addon initialization."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
ADDON = ROOT / "src/core/modules/sol_laboratory"
PREFIX = "odoo.addons.sol_laboratory"


def load_service(name):
    namespaces = {}
    for package in ("odoo", "odoo.addons", PREFIX, f"{PREFIX}.constants", f"{PREFIX}.services"):
        module = ModuleType(package)
        module.__path__ = []
        namespaces[package] = module
    http = ModuleType("odoo.http")
    http.request = None
    namespaces["odoo.http"] = http
    with patch.dict(sys.modules, namespaces):
        _load(f"{PREFIX}.constants.laboratory_editing", ADDON / "constants/laboratory_editing.py")
        return _load(f"{PREFIX}.services.{name}", ADDON / "services" / f"{name}.py")


def _load(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise ImportError(name)
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module
