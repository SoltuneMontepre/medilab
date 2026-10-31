"""Render field descriptors and relational mapped paths from registry metadata."""

from type_names import model_type

SCALAR = {
    "boolean": "bool",
    "integer": "int",
    "float": "float",
    "monetary": "float",
    "char": "str | Literal[False]",
    "text": "str | Literal[False]",
    "html": "str | Literal[False]",
    "selection": "str | Literal[False]",
    "date": "_datetime.date | Literal[False]",
    "datetime": "_datetime.datetime | Literal[False]",
    "binary": "BinaryValue",
    "json": "object",
    "properties": "object",
    "properties_definition": "object",
    "reference": "BaseModel | Literal[False]",
    "many2one_reference": "int",
    "id": "int",
}


def field_map(name, model, field_keys):
    lines = []
    field_classes = {
        "boolean": "Boolean",
        "integer": "Integer",
        "float": "Float",
        "monetary": "Monetary",
        "char": "Char",
        "text": "Text",
        "html": "Html",
        "selection": "Selection",
        "date": "Date",
        "datetime": "Datetime",
        "binary": "Binary",
        "json": "Json",
        "properties": "Properties",
        "properties_definition": "PropertiesDefinition",
        "reference": "Reference",
        "many2one_reference": "Many2oneReference",
        "many2one": "Many2one",
        "one2many": "One2many",
        "many2many": "Many2many",
    }
    keys = sorted(set(field_keys) & set(model["fields"]))
    if keys:
        lines.append(f"class _Fields_{model_type(name)}(dict[str, Field]):")
        for key in keys:
            native = (
                "Id" if key == "id" else field_classes[model["fields"][key]["type"]]
            )
            lines.extend(
                [
                    "    @overload",
                    f"    def __getitem__(self, key: Literal[{key!r}], /) -> _native_fields.{native}: ...",
                ]
            )
        lines.extend(
            [
                "    @overload",
                "    def __getitem__(self, key: str, /) -> Field: ...",
            ]
        )
    return lines, keys


def field_members(name, model, registry):
    members = []
    for key, field in sorted(model["fields"].items()):
        if not key.isidentifier() or key == "id":
            continue
        comodel = field["comodel"]
        if comodel:
            if comodel == "_unknown" or comodel not in registry:
                raise ValueError(f"Unknown relation target: {name}.{key} -> {comodel}")
            value = model_type(comodel)
        else:
            try:
                value = SCALAR[field["type"]]
            except KeyError as error:
                raise ValueError(
                    f"Unsupported field type: {name}.{key}: {field['type']}"
                ) from error
        write = value + " | None"
        if field["type"] == "many2one":
            write += " | int | Literal[False]"
        elif field["type"] in ("one2many", "many2many"):
            write += " | Iterable[CommandValue] | Iterable[int] | Literal[False]"
        elif field["type"] in ("date", "datetime", "binary"):
            write += " | str"
            if field["type"] == "binary":
                write += " | Literal[False]"
                if key == "raw":
                    write += " | bytes"
        members.append(f"    {key}: _RegistryField[{value}, {write}]")
    return members


def mapped_members(model, mapped_paths, registry):
    members = []
    for path in sorted(set(mapped_paths)):
        current = model
        final = None
        for position, part in enumerate(path.split(".")):
            final = current["fields"].get(part)
            if final is None:
                break
            if position < len(path.split(".")) - 1:
                if not final["comodel"]:
                    final = None
                    break
                current = registry[final["comodel"]]
        if final is None:
            continue
        target = model_type(final["comodel"]) if final["comodel"] else None
        if target:
            result = target
        else:
            result = (
                "list[IdType | Literal[False]]"
                if path == "id"
                else f"list[{SCALAR[final['type']]}]"
            )
        members.extend(
            [
                "    @overload",
                f"    def mapped(self, func: Literal[{path!r}]) -> {result}: ...",
            ]
        )
    if any("def mapped(" in member for member in members):
        members.append("    @overload")
    members.append(
        "    def mapped(self, func: str | Callable[[Self], R]) -> list[R] | BaseModel: ..."
    )
    return members
