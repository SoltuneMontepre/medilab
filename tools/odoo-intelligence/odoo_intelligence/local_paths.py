"""Reuse the private-state policy of a trusted MediLab checkout."""

import importlib.util
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=4)
def path_policy(root: Path):
    source = Path(__file__).resolve().parents[2] / "scripts/local_private_paths.py"
    if not source.is_file():
        source = root / "tools/scripts/local_private_paths.py"
    if not source.is_file():
        raise RuntimeError("This checkout lacks its private local-state helper; update the checkout before setup.")
    spec = importlib.util.spec_from_file_location("medilab_local_private_paths", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("The private local-state helper could not be loaded.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ensure_directory(root: Path, directory: Path) -> Path:
    return path_policy(root).ensure_local_directory(root, directory)
