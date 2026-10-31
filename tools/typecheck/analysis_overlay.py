"""Build an annotation-only Odoo mirror; retain imports of the original MediLab method bodies."""

import ast
import json
import os
import shutil

from framework_annotations import apply
from generate_types import core_model_methods, model_type, write_package
from link_addons import is_link


def environment_source(source, registry, external_ids=None):
    tree = ast.parse(source)
    environment = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Environment"
    )
    lookup = next(
        node
        for node in environment.body
        if isinstance(node, ast.FunctionDef) and node.name == "__getitem__"
    )
    declarations = [
        "    @typing.overload\n"
        f"    def __getitem__(self, model_name: typing.Literal[{name!r}]) -> _model_types.{model_type(name)}: ...\n"
        for name in sorted(registry)
    ]
    declarations.append(
        "    @typing.overload\n"
        "    def __getitem__(self, model_name: _DynamicModelName) -> _model_types.Model_base: ...\n"
    )
    lines = source.splitlines(keepends=True)
    lines.insert(lookup.lineno - 1, "".join(declarations))
    result = "".join(lines)
    if external_ids:
        updated = ast.parse(result)
        environment = next(
            node
            for node in updated.body
            if isinstance(node, ast.ClassDef) and node.name == "Environment"
        )
        ref = next(
            node
            for node in environment.body
            if isinstance(node, ast.FunctionDef) and node.name == "ref"
        )
        position = (
            min([ref.lineno, *[decorator.lineno for decorator in ref.decorator_list]])
            - 1
        )
        references = []
        for xml_id, model in sorted(external_ids.items()):
            if model not in registry:
                continue
            target = f"_model_types.{model_type(model)}"
            references.extend(
                [
                    (
                        "    @typing.overload\n"
                        f"    def ref(self, xml_id: typing.Literal[{xml_id!r}], raise_if_not_found: typing.Literal[True] = True) -> {target}: ...\n"
                    ),
                    (
                        "    @typing.overload\n"
                        f"    def ref(self, xml_id: typing.Literal[{xml_id!r}], raise_if_not_found: typing.Literal[False]) -> {target} | None: ...\n"
                    ),
                ]
            )
        lines = result.splitlines(keepends=True)
        lines.insert(position, "".join(references))
        result = "".join(lines)
    # The generated import belongs after future imports and before other executable statements.
    import_position = next(
        node.lineno - 1
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and getattr(node, "module", "") != "__future__"
    )
    lines = result.splitlines(keepends=True)
    lines.insert(
        import_position,
        "import typing\nif typing.TYPE_CHECKING:\n    import medilab_model_types as _model_types\n    from medilab_model_types import DynamicModelName as _DynamicModelName\n",
    )
    result = "".join(lines)
    for member, model in (
        ("user", "res.users"),
        ("company", "res.company"),
        ("companies", "res.company"),
    ):
        result = result.replace(
            f"def {member}(self) -> BaseModel:",
            f"def {member}(self) -> _model_types.{model_type(model)}:",
        )
    ast.parse(result)
    return result


def prepare(root, registry_directory, destination, published_path=None):
    destination = destination.resolve()
    if published_path is not None:
        published_path = published_path.resolve()
    registry = json.loads(
        (registry_directory / "registry.json").read_text(encoding="utf-8")
    )
    strings, mapped_paths, field_keys = set(), set(), set()
    for source in (root / "src/core/modules").rglob("*.py"):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        strings.update(
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        )
        mapped_paths.update(
            node.args[0].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "mapped"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        )
        field_keys.update(
            node.slice.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "_fields"
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        )
    xmlids = json.loads(
        (registry_directory / "xmlids.json").read_text(encoding="utf-8")
    )
    external_ids = {key: value for key, value in xmlids.items() if key in strings}
    destination.mkdir(parents=True, exist_ok=False)
    write_package(
        registry,
        destination / "medilab_model_types",
        mapped_paths,
        core_model_methods(
            (root / ".local/odoo-source/odoo/orm/models.py").read_text(encoding="utf-8")
        ),
        field_keys,
    )
    mirror = destination / "odoo-source"
    original_odoo = root / ".local/odoo-source/odoo"
    shutil.copytree(
        original_odoo,
        mirror / "odoo",
        symlinks=True,
        ignore=lambda directory, names: (
            [name for name in names if is_link(original_odoo / "addons" / name)]
            if os.path.normpath(directory)
            == os.path.normpath(str(original_odoo / "addons"))
            else []
        ),
    )
    addons = mirror / "odoo/addons"

    def link(target, source):
        if os.name == "nt":
            shutil.copytree(source, target)
        else:
            target.symlink_to(source.resolve(), target_is_directory=True)

    for original in (original_odoo / "addons").iterdir():
        if is_link(original):
            link(addons / original.name, original.resolve(strict=True))
    for addon in sorted((root / ".local/odoo-source/addons").iterdir()):
        target = addons / addon.name
        if addon.is_dir() and not target.exists():
            link(target, addon)
    path = mirror / "odoo/orm/environments.py"
    path.write_text(
        environment_source(path.read_text(encoding="utf-8"), registry, external_ids),
        encoding="utf-8",
    )
    apply(mirror)
    config = json.loads((root / "pyrightconfig.json").read_text(encoding="utf-8"))
    visible = published_path or destination
    config.update(
        {
            "include": [
                os.path.relpath(root / "src/core/modules", visible),
                "medilab_model_types/**/*.pyi",
            ],
            "exclude": [
                os.path.relpath(path, visible)
                for path in sorted(
                    (root / "src/core/modules").glob("*/__manifest__.py")
                )
            ],
            "extraPaths": [str(visible / "odoo-source"), str(visible)],
            "venvPath": str(root / "src/core"),
        }
    )
    (destination / "pyrightconfig.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
