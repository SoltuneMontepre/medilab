"""Bind source method signatures without replacing or omitting their bodies."""


def method_contracts(name, model):
    members = []
    overrides = set()
    if name == "ir.actions.report":
        overrides.add("_get_report")
        members.append(
            "    def _get_report(self, report_ref: str | int | Self) -> Self: ..."
        )
    if name == "ir.config_parameter":
        for getter, value_type in (
            ("get_int", "int"),
            ("get_float", "float"),
            ("get_str", "str"),
            ("get_bool", "bool"),
        ):
            overrides.add(getter)
            members.extend(
                [
                    "    @overload",
                    f"    def {getter}(self, key: str) -> {value_type}: ...",
                    "    @overload",
                    f"    def {getter}[T](self, key: str, default: T) -> {value_type} | T: ...",
                ]
            )
    if name == "res.config.settings" and "_get_parameter" in model["methods"]:
        overrides.add("_get_parameter")
        for key, metadata in sorted(model["fields"].items()):
            if metadata["type"] not in (
                "boolean",
                "integer",
                "float",
                "monetary",
                "char",
                "text",
                "selection",
            ):
                continue
            result = {
                "boolean": "bool",
                "integer": "int",
                "float": "float",
                "monetary": "float",
                "char": "str",
                "text": "str",
                "selection": "str",
            }[metadata["type"]]
            default = metadata.get("defaultType", "object")
            if default != result:
                result += f" | {default}"
            members.extend(
                [
                    "    @overload",
                    f"    def _get_parameter(self, field_name: Literal[{key!r}]) -> {result}: ...",
                ]
            )
        members.extend(
            [
                "    @overload",
                "    def _get_parameter(self, field_name: str) -> object: ...",
            ]
        )
    return members, overrides


def method_members(model, imports, core_methods, overrides):
    members = []
    for key, method in sorted(model["methods"].items()):
        if (
            key.startswith(("__", f"_{method['class']}__"))
            or key in overrides
            or key in core_methods
            or key
            in {
                "mapped",
                "browse",
                "search",
                "search_fetch",
                "sudo",
                "with_env",
                "with_user",
                "with_context",
                "with_company",
                "with_prefetch",
                "filtered",
                "filtered_domain",
                "sorted",
                "exists",
                "ensure_one",
                "create",
                "copy",
            }
            or key in model["fields"]
            or method["module"] not in imports
        ):
            continue
        owner = method["class"]
        if not owner.isidentifier():
            continue
        wrapper = (
            "_method"
            if method.get("binding", "instance") == "instance"
            else "staticmethod"
        )
        if wrapper == "_method" and method.get("returnsSelf"):
            wrapper = "_self_method"
        members.append(
            f"    {key} = {wrapper}({imports[method['module']]}.{owner}.{key})"
        )
    return members
