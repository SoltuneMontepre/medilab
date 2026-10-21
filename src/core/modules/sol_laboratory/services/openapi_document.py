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
def document():
    with open(file_path(DOCUMENT_PATH), encoding="utf-8") as handle:
        return yaml.safe_load(handle)


@functools.cache
def operations():
    """Each operation of the document by its operationId: its method, its path and the operation."""
    return {
        operation["operationId"]: (method.upper(), path, operation)
        for path, item in document()["paths"].items()
        for method, operation in item.items()
        if method in OPERATION_METHODS
    }


@functools.cache
def _registry():
    return Registry().with_resource(DOCUMENT_URI, Resource(contents=document(), specification=DRAFT202012))


@functools.cache
def _validator(pointer):
    """The validator of the schema at the JSON pointer of the document, whose references resolve in the document."""
    return Draft202012Validator({"$ref": f"{DOCUMENT_URI}#{pointer}"}, registry=_registry())


def _pointer(*parts):
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def schema_error(pointer, value):
    """What makes the value break the schema at the pointer, or None when it matches it."""
    error = best_match(_validator(pointer).iter_errors(value))
    if error is None:
        return None
    where = "/".join(str(part) for part in error.absolute_path)
    return f"{where}: {error.message}" if where else error.message


def request_body_pointer(operation_id):
    """The pointer of the JSON body the operation takes, or None when it takes none."""
    method, path, operation = operations()[operation_id]
    if "requestBody" not in operation:
        return None
    return _pointer("paths", path, method.lower(), "requestBody", "content", "application/json", "schema")


def documented_answer(operation_id, status):
    """The answer the operation documents for the status, or None when it documents none."""
    _method, _path, operation = operations()[operation_id]
    answer = operation["responses"].get(str(status))
    if answer and "$ref" in answer:
        return document()["components"]["responses"][answer["$ref"].rsplit("/", 1)[1]]
    return answer


def answer_pointer(operation_id, status):
    """The pointer of the JSON body of the operation's documented answer with the status, or None when it has none."""
    method, path, operation = operations()[operation_id]
    answer = operation["responses"][str(status)]
    if "$ref" in answer:
        name = answer["$ref"].rsplit("/", 1)[1]
        answer, parts = document()["components"]["responses"][name], ("components", "responses", name)
    else:
        parts = ("paths", path, method.lower(), "responses", str(status))
    if "content" not in answer:
        return None
    return _pointer(*parts, "content", "application/json", "schema")


def required_headers(answer):
    """The headers a documented answer must carry."""
    headers = answer.get("headers", {}).items()
    return [name for name, header in headers if _component("headers", header).get("required")]


def _component(kind, value):
    if "$ref" in value:
        return document()["components"][kind][value["$ref"].rsplit("/", 1)[1]]
    return value
