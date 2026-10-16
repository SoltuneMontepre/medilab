"""Split the test classes of the given modules into shards with about the same number of test methods.

Usage: python3 test_shards.py <module,module> <shard count> <output dir>
Writes <output dir>/<n>.txt for n from 1, each holding the Odoo --test-tags of that shard.
"""

import ast
import sys
from pathlib import Path

ADDONS_DIR = Path("/mnt/extra-addons")


def test_classes(module):
    """Yield the test tag and the number of its own test methods for every class in the module's tests package."""
    for path in sorted((ADDONS_DIR / module / "tests").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef):
                methods = sum(
                    isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test")
                    for item in node.body
                )
                yield f"/{module}:{node.name}", methods


def main(modules, shard_count, output_dir):
    weights = {}
    for module in modules.split(","):
        for tag, methods in test_classes(module):
            weights[tag] = max(weights.get(tag, 0), methods)

    shards = [[] for _ in range(shard_count)]
    loads = [0] * shard_count
    for tag in sorted(weights, key=lambda tag: (-weights[tag], tag)):
        lightest = loads.index(min(loads))
        shards[lightest].append(tag)
        loads[lightest] += weights[tag]

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    for number, tags in enumerate(shards, start=1):
        (output / f"{number}.txt").write_text(",".join(tags), encoding="utf-8")
        print(f"Shard {number}: {len(tags)} classes, {loads[number - 1]} tests.")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), sys.argv[3])
