"""The OpenAPI document of the laboratory files API, and the checks of requests and answers against it."""

import functools

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from odoo.tools.misc import file_path

DOCUMENT_PATH = "sol_laboratory/api/openapi.yaml"
# The address the schemas of the document refer to each other under, as #/components/schemas/<name>.
DOCUMENT_URI = "urn:medilab:laboratory-files-api"
# The schema every refusal answers with.
ERROR_SCHEMA = "/components/schemas/Error"
OPERATION_METHODS = ("get", "put", "post", "delete", "patch", "head", "options", "trace")


@functools.cache
def document(document_path=DOCUMENT_PATH):
    with open(file_path(document_path), encoding="utf-8") as handle:
        return yaml.safe_load(handle)


@functools.cache
def operations(document_path=DOCUMENT_PATH):
    """Each operation of the document by its operationId: its method, its path and the operation."""
    return {
        operation["operationId"]: (method.upper(), path, operation)
        for path, item in document(document_path)["paths"].items()
        for method, operation in item.items()
        if method in OPERATION_METHODS
    }


@functools.cache
def _registry(document_path=DOCUMENT_PATH, document_uri=DOCUMENT_URI):
    return Registry().with_resource(document_uri, Resource(contents=document(document_path), specification=DRAFT202012))


@functools.cache
def _validator(pointer, document_path=DOCUMENT_PATH, document_uri=DOCUMENT_URI):
    """The validator of the schema at the JSON pointer of the document, whose references resolve in the document."""
    return Draft202012Validator({"$ref": f"{document_uri}#{pointer}"}, registry=_registry(document_path, document_uri))


def _pointer(*parts):
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def schema_error(pointer, value, *, document_path=DOCUMENT_PATH, document_uri=DOCUMENT_URI):
    """What makes the value break the schema at the pointer, or None when it matches it."""
    error = best_match(_validator(pointer, document_path, document_uri).iter_errors(value))
    if error is None:
        return None
    where = "/".join(str(part) for part in error.absolute_path)
    return f"{where}: {error.message}" if where else error.message


def request_body_pointer(operation_id, *, document_path=DOCUMENT_PATH):
    """The pointer of the JSON body the operation takes, or None when it takes none."""
    method, path, operation = operations(document_path)[operation_id]
    if "requestBody" not in operation:
        return None
    return _pointer("paths", path, method.lower(), "requestBody", "content", "application/json", "schema")


def parameters(operation_id):
    """The query and header parameters the operation takes: each one's name, where it is sent, whether it is required
    and the pointer of its schema."""
    method, path, operation = operations()[operation_id]
    found = []
    for index, parameter in enumerate(operation.get("parameters", [])):
        if "$ref" in parameter:
            name = parameter["$ref"].rsplit("/", 1)[1]
            parameter, pointer = (
                document()["components"]["parameters"][name],
                _pointer("components", "parameters", name),
            )
        else:
            pointer = _pointer("paths", path, method.lower(), "parameters", index)
        if parameter["in"] in ("query", "header"):
            found.append((parameter["name"], parameter["in"], parameter.get("required", False), pointer + "/schema"))
    return found


def documented_answer(operation_id, status, *, document_path=DOCUMENT_PATH):
    """The answer the operation documents for the status, or None when it documents none."""
    _method, _path, operation = operations(document_path)[operation_id]
    answer = operation["responses"].get(str(status))
    if answer and "$ref" in answer:
        return document(document_path)["components"]["responses"][answer["$ref"].rsplit("/", 1)[1]]
    return answer


def answer_pointer(operation_id, status, *, document_path=DOCUMENT_PATH):
    """The pointer of the JSON body of the operation's documented answer with the status, or None when it has none."""
    method, path, operation = operations(document_path)[operation_id]
    answer = operation["responses"][str(status)]
    if "$ref" in answer:
        name = answer["$ref"].rsplit("/", 1)[1]
        answer, parts = document(document_path)["components"]["responses"][name], ("components", "responses", name)
    else:
        parts = ("paths", path, method.lower(), "responses", str(status))
    if "content" not in answer:
        return None
    return _pointer(*parts, "content", "application/json", "schema")


def required_headers(answer, *, document_path=DOCUMENT_PATH):
    """The headers a documented answer must carry."""
    headers = answer.get("headers", {}).items()
    return [name for name, header in headers if _component("headers", header, document_path).get("required")]


def _component(kind, value, document_path=DOCUMENT_PATH):
    if "$ref" in value:
        return document(document_path)["components"][kind][value["$ref"].rsplit("/", 1)[1]]
    return value
