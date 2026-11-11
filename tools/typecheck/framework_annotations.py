"""Annotation corrections for the pinned Odoo source, applied only to the analysis mirror."""

import ast
import shutil


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError(
            f"The pinned Odoo source no longer matches the typing correction: {old}"
        )
    return source.replace(old, new, 1)


def imports(source, additions):
    tree = ast.parse(source)
    position = next(
        node.lineno - 1
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and getattr(node, "module", "") != "__future__"
    )
    lines = source.splitlines(keepends=True)
    lines.insert(position, additions + "\n")
    return "".join(lines)


def assertions(source):
    source = imports(
        source,
        "import typing as _typing\nimport unittest as _unittest\n"
        "_ExceptionT = _typing.TypeVar('_ExceptionT', bound=BaseException)\n"
        "_Params = _typing.ParamSpec('_Params')",
    )
    for name, extra in (
        ("assertRaises", ""),
        ("assertRaisesRegex", "expected_regex: str, "),
    ):
        needle = f"    def {name}(self, expected_exception, "
        if extra:
            needle += "expected_regex, "
        needle += "callable=None, *args, **kwargs):"
        prefix = (
            f"    def {name}(self, expected_exception: type[_ExceptionT] | tuple[type[_ExceptionT], ...], "
            f"{extra}"
        )
        overloads = (
            "    @_typing.overload\n"
            + prefix
            + "callable: None = None, *, msg: str | None = None) -> "
            "_typing.ContextManager[_unittest.case._AssertRaisesContext[_ExceptionT]]: ...\n"
            "    @_typing.overload\n"
            + prefix
            + "callable: _typing.Callable[_Params, object], "
            "*args: _Params.args, **kwargs: _Params.kwargs) -> None: ...\n"
        )
        source = replace_once(source, needle, overloads + needle)
    return source


def selection(source):
    return replace_once(
        source,
        "def __init__(self, selection=SENTINEL, string: str | Sentinel = SENTINEL, **kwargs):",
        "def __init__(self, selection: list[SelectValue] | tuple[SelectValue, ...] | str | "
        "Callable[[BaseModel], list[SelectValue]] | None | Sentinel = SENTINEL, "
        "string: str | Sentinel = SENTINEL, **kwargs):",
    )


def context_mapping(source):
    source = replace_once(
        source, "class frozendict[K, V]:", "class frozendict[K, V](Mapping[K, V]):"
    )
    for name, value in (
        ("format_date", "datetime.datetime | datetime.date | str"),
        ("format_datetime", "datetime.datetime | str"),
    ):
        source = replace_once(
            source,
            f"def {name}(\n    env: Environment,\n    value: {value},",
            f"def {name}(\n    env: Environment,\n    value: {value} | typing.Literal[False] | None,",
        )
    source = replace_once(
        source, "context: dict[str, typing.Any]", "context: Mapping[str, typing.Any]"
    )
    return source


def identifier(source):
    source = imports(
        source, "if typing.TYPE_CHECKING:\n    from .models import BaseModel"
    )
    tree = ast.parse(source)
    identifier_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Id"
    )
    getter = next(
        node
        for node in identifier_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "__get__"
    )
    lines = source.splitlines(keepends=True)
    lines.insert(
        getter.lineno - 1,
        "    @typing.overload\n"
        "    def __get__(self, record: None, owner=None) -> typing.Self: ...\n"
        "    @typing.overload\n"
        "    def __get__(self, record: BaseModel, owner=None) -> IdType | typing.Literal[False]: ...\n",
    )
    return "".join(lines)


def request_members(source):
    source = imports(
        source,
        "from .session import Session as _Session\nimport werkzeug.wrappers as _wrappers",
    )
    tree = ast.parse(source)
    request = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Request"
    )
    init = next(
        node
        for node in request.body
        if isinstance(node, ast.FunctionDef) and node.name == "__init__"
    )
    lines = source.splitlines(keepends=True)
    lines.insert(
        init.lineno - 1, "    session: _Session\n    httprequest: _wrappers.Request\n\n"
    )
    return replace_once(
        "".join(lines),
        "    def make_response(self,\n        data: str,",
        "    def make_response(self,\n        data: str | bytes,",
    )


def model_contracts(source):
    source = replace_once(
        source,
        "ids: int | typing.Iterable[IdType] = ()",
        "ids: int | typing.Literal[False] | None | typing.Iterable[IdType] = ()",
    )
    source = replace_once(
        source,
        "AbstractModel = BaseModel",
        "class AbstractModel(BaseModel):\n    _register = False",
    )
    tree = ast.parse(source)
    model = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "BaseModel"
    )
    method = next(node for node in model.body if isinstance(node, ast.FunctionDef))
    position = (
        min([method.lineno, *[decorator.lineno for decorator in method.decorator_list]])
        - 1
    )
    lines = source.splitlines(keepends=True)
    lines.insert(position, "    _original_module: typing.ClassVar[str | None]\n\n")
    return "".join(lines)


def form_contracts(source):
    source = replace_once(source, "class Form:", "class Form[_RecordT: BaseModel]:")
    source = replace_once(
        source,
        "    def __init__(self, record: BaseModel,",
        "    _record: _RecordT\n\n    def __init__(self, record: _RecordT,",
    )
    return source


def sql_contracts(source):
    generic = "    @typing.overload\n    def __new__[T: SQL](cls: type[T], *a, **kw) -> T:\n        ...\n\n"
    source = replace_once(source, generic, "")
    return replace_once(
        source,
        "    def __new__(cls, *a, **kw):",
        generic + "    def __new__(cls, *a, **kw):",
    )


def quant_contracts(source):
    source = imports(source, "import typing")
    return replace_once(
        source,
        "def _update_available_quantity(self, product_id, location_id, quantity=False, reserved_quantity=False,",
        "def _update_available_quantity(self, product_id, location_id, quantity: float | typing.Literal[False]=False, reserved_quantity: float | typing.Literal[False]=False,",
    )


def apply(mirror):
    for relative, transform in (
        ("odoo/tests/common.py", assertions),
        ("odoo/tests/form.py", form_contracts),
        ("odoo/orm/models.py", model_contracts),
        ("odoo/tools/sql.py", sql_contracts),
        ("odoo/orm/fields_selection.py", selection),
        ("odoo/tools/misc.py", context_mapping),
        ("odoo/http/requestlib.py", request_members),
        ("odoo/orm/fields_misc.py", identifier),
    ):
        path = mirror / relative
        path.write_text(transform(path.read_text(encoding="utf-8")), encoding="utf-8")

    routing = mirror / "odoo/http/routing_map.py"
    routing.write_text(
        replace_once(
            routing.read_text(encoding="utf-8"),
            "'OPTIONS', 'PATCH']",
            "'OPTIONS', 'PATCH', 'TRACE', 'CONNECT']",
        ),
        encoding="utf-8",
    )
    stock = mirror / "odoo/addons/stock"
    if stock.is_symlink():
        replacement = stock.with_name(".stock-typing")
        shutil.copytree(stock.resolve(), replacement)
        stock.unlink()
        replacement.rename(stock)
    quant = stock / "models/stock_quant.py"
    quant.write_text(
        quant_contracts(quant.read_text(encoding="utf-8")), encoding="utf-8"
    )
