"""Generate registry field interfaces without replacing the Python sources being checked."""

import argparse
import ast
import json
from pathlib import Path

from generated_fields import field_map, field_members, mapped_members
from generated_header import preamble
from generated_methods import method_contracts, method_members
from type_names import model_type

RUNTIME_GUARD = 'raise RuntimeError("Registry types are for TYPE_CHECKING only.")\n'


def mapped_relations(model, mapped_paths, registry):
    related = set()
    for path in mapped_paths:
        current = model
        for part in path.split("."):
            metadata = current["fields"].get(part)
            if not metadata or not metadata["comodel"]:
                break
            target = metadata["comodel"]
            related.add(target)
            current = registry[target]
    return related


def related_models(chosen, mapped_paths, registry):
    related = {
        field["comodel"]
        for model in chosen.values()
        for field in model["fields"].values()
        if field["comodel"]
    }
    for model in chosen.values():
        related.update(mapped_relations(model, mapped_paths, registry))
    return related - chosen.keys()


def model_members(name, model, registry, imports, mapped_paths, core_methods, keys):
    members = [f"    _name: ClassVar[Literal[{name!r}]]"]
    if model.get("originalModule") is not None:
        members.append(
            f"    _original_module: ClassVar[Literal[{model['originalModule']!r}]]"
        )
    for key, attribute in sorted(model.get("attributes", {}).items()):
        members.append(
            f"    {key} = {imports[attribute['module']]}.{attribute['class']}.{key}"
        )
    if keys:
        members.append(f"    _fields: ClassVar[_Fields_{model_type(name)}]")
    contracts, overrides = method_contracts(name, model)
    members.extend(contracts)
    members.extend(field_members(name, model, registry))
    members.extend(mapped_members(model, mapped_paths, registry))
    members.extend(method_members(model, imports, core_methods, overrides))
    return members


def render(registry, selected=None, mapped_paths=(), core_methods=(), field_keys=()):
    chosen = (
        registry if selected is None else {name: registry[name] for name in selected}
    )
    names = [model_type(name) for name in registry]
    if len(set(names)) != len(names):
        raise ValueError("Model names produce colliding Python type names.")
    owners = sorted(
        {
            method["module"]
            for model in chosen.values()
            for method in model["methods"].values()
            if method["module"].startswith("odoo.addons.")
        }
    )
    owners = sorted(
        set(owners)
        | {
            attribute["module"]
            for model in chosen.values()
            for attribute in model.get("attributes", {}).values()
        }
    )
    imports = {owner: f"_source_{index}" for index, owner in enumerate(owners)}
    lines = preamble(imports)
    if selected is not None:
        related = related_models(chosen, mapped_paths, registry)
        if related:
            lines.append("if TYPE_CHECKING:")
            lines.extend(
                f"    from ._{model_type(name).lower()} import {model_type(name)}"
                for name in sorted(related)
            )
    for name, model in sorted(chosen.items()):
        field_lines, keys = field_map(name, model, field_keys)
        lines.extend(field_lines)
        lines.append(f"class {model_type(name)}(BaseModel):")
        members = model_members(
            name, model, registry, imports, mapped_paths, core_methods, keys
        )
        lines.extend(members or ["    pass"])
    return "\n".join(lines) + "\n"


def core_model_methods(source):
    tree = ast.parse(source)
    base = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "BaseModel"
    )
    return {
        node.name
        for node in base.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def write_package(registry, directory, mapped_paths=(), core_methods=(), field_keys=()):
    directory.mkdir(parents=True, exist_ok=False)
    exports = []
    for name in sorted(registry):
        symbol = model_type(name)
        (directory / f"_{symbol.lower()}.pyi").write_text(
            render(registry, [name], mapped_paths, core_methods, field_keys),
            encoding="utf-8",
        )
        (directory / f"_{symbol.lower()}.py").write_text(
            RUNTIME_GUARD,
            encoding="utf-8",
        )
        exports.append(f"from ._{symbol.lower()} import {symbol} as {symbol}")
    (directory / "_lookup.pyi").write_text(
        'from typing import NewType\nDynamicModelName = NewType("DynamicModelName", str)\n',
        encoding="utf-8",
    )
    (directory / "_lookup.py").write_text(
        RUNTIME_GUARD,
        encoding="utf-8",
    )
    exports.append("from ._lookup import DynamicModelName as DynamicModelName")
    versioned = [
        model_type(name)
        for name, model in sorted(registry.items())
        if all(
            method in model["methods"]
            for method in (
                "_change_request_open",
                "_new_version",
                "_approval_department",
            )
        )
    ]
    exports.extend(
        [
            "from typing import Never, TypeAlias",
            "VersionedDocument: TypeAlias = "
            + (" | ".join(versioned) if versioned else "Never"),
        ]
    )
    cleanup = [
        model_type(name)
        for name, model in sorted(registry.items())
        if "_cleanup_domain" in model["methods"]
    ]
    exports.append(
        "CleanupDocument: TypeAlias = " + (" | ".join(cleanup) if cleanup else "Never")
    )
    (directory / "__init__.pyi").write_text("\n".join(exports) + "\n", encoding="utf-8")
    (directory / "__init__.py").write_text(
        RUNTIME_GUARD,
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source = (
        Path(__file__).resolve().parents[2] / ".local/odoo-source/odoo/orm/models.py"
    )
    write_package(
        json.loads(args.registry.read_text(encoding="utf-8")),
        args.output,
        core_methods=core_model_methods(source.read_text(encoding="utf-8")),
    )


if __name__ == "__main__":
    main()
