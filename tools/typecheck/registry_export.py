"""Export the installed registry inside an Odoo shell; never invoke model business methods."""

import hashlib
import inspect
import json
import os
from pathlib import Path
from typing import Self


def default_type(field):
    value = getattr(field, "default", None)
    if (
        inspect.isfunction(value)
        and value.__module__ == "odoo.orm.fields"
        and value.__qualname__ == "Field._setup_attrs__.<locals>.<lambda>"
    ):
        value = inspect.getclosurevars(value).nonlocals["value"]
    if value is None:
        return "None"
    if value is False:
        return "Literal[False]"
    return type(value).__name__ if type(value) in (str, int, float, bool) else "object"


def stable_signature(signature):
    parameters = [
        parameter
        if parameter.default is inspect.Parameter.empty
        or type(parameter.default) in (str, bytes, bool, int, float, type(None))
        else parameter.replace(default=Ellipsis)
        for parameter in signature.parameters.values()
    ]
    return str(signature.replace(parameters=parameters))


def export_registry(environment):
    result = {}
    for name in sorted(environment.registry):
        model = environment[name]
        fields = {
            key: {
                "type": field.type,
                "comodel": getattr(field, "comodel_name", None),
                "required": field.required,
                "related": field.related,
                "defaultType": default_type(field),
            }
            for key, field in sorted(model._fields.items())
        }
        methods = {}
        attributes = {}
        for base in reversed(type(model).__mro__):
            for key, value in sorted(vars(base).items()):
                if (
                    key in ("_permission_actions", "_audit_children")
                    and base.__module__.startswith("odoo.addons.")
                    and base.__name__.isidentifier()
                ):
                    attributes[key] = {
                        "module": base.__module__,
                        "class": base.__name__,
                    }
                binding = "instance"
                if isinstance(value, (classmethod, staticmethod)):
                    binding = "class" if isinstance(value, classmethod) else "static"
                    value = value.__func__
                if not inspect.isfunction(value):
                    continue
                try:
                    inspected_signature = inspect.signature(value)
                    signature = stable_signature(inspected_signature)
                    returns_self = (
                        inspected_signature.return_annotation is Self
                        or inspected_signature.return_annotation
                        in ("Self", "typing.Self")
                    )
                    source = inspect.getsourcefile(inspect.unwrap(value))
                except (TypeError, ValueError):
                    signature, source, returns_self = None, None, False
                methods[key] = {
                    "signature": signature,
                    "source": source,
                    "class": base.__name__,
                    "module": base.__module__,
                    "binding": binding,
                    "returnsSelf": returns_self,
                }
        bases = [
            {
                "module": base.__module__,
                "name": base.__name__,
                "model": getattr(base, "_name", None),
            }
            for base in type(model).__mro__
            if base.__module__.startswith("odoo.addons.") and "." not in base.__name__
        ]
        result[name] = {
            "fields": fields,
            "methods": methods,
            "inherits": dict(model._inherits),
            "bases": bases,
            "attributes": attributes,
            "abstract": bool(getattr(model, "_abstract", False)),
            "originalModule": getattr(model, "_original_module", None),
        }
    return result


def source_hashes(registry, root):
    paths = {
        Path(method["source"]).resolve()
        for model in registry.values()
        for method in model["methods"].values()
        if method["source"] is not None
    }
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
        if path.is_relative_to(root)
    }


if __name__ == "__main__":
    expected_modules = set(os.environ["MEDILAB_TYPECHECK_MODULES"].split(","))
    installed = globals()["env"]["ir.module.module"].search_read(
        [("name", "in", sorted(expected_modules)), ("state", "=", "installed")],
        ["name"],
    )
    if {module["name"] for module in installed} != expected_modules:
        raise RuntimeError(
            "Not every requested module was installed in the typing database."
        )
    # Odoo shell supplies env; this file is executed, rather than imported, there.
    snapshot = export_registry(globals()["env"])
    Path("/output/registry.json").write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    external_ids = {
        f"{record['module']}.{record['name']}": record["model"]
        for record in globals()["env"]["ir.model.data"].search_read(
            [], ["module", "name", "model"]
        )
    }
    Path("/output/xmlids.json").write_text(
        json.dumps(external_ids, sort_keys=True) + "\n", encoding="utf-8"
    )

    import odoo.orm.environments

    hashes = source_hashes(
        snapshot, Path(odoo.orm.environments.__file__).resolve().parents[1]
    )
    Path("/output/source-hashes.json").write_text(
        json.dumps(hashes, sort_keys=True) + "\n", encoding="utf-8"
    )
