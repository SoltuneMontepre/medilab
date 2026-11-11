"""Resolve model names obtained from document metadata rather than known model constants."""

from typing import TYPE_CHECKING, Literal, NewType, TypeGuard, overload

from odoo.api import Environment
from odoo.models import BaseModel

if TYPE_CHECKING:
    from medilab_model_types import CleanupDocument, DynamicModelName, VersionedDocument
    from medilab_model_types import Model_base as DynamicModel
else:
    VersionedDocument = BaseModel
    CleanupDocument = BaseModel
    DynamicModelName = NewType("DynamicModelName", str)
    DynamicModel = BaseModel


def dynamic_model(environment: Environment, name: str | Literal[False]) -> DynamicModel:
    if not name:
        raise KeyError(name)
    return environment[DynamicModelName(name)]


def is_versioned_document(record: BaseModel) -> TypeGuard[VersionedDocument]:
    return all(
        callable(getattr(record, method, None))
        for method in (
            "_change_request_open",
            "_new_version",
            "_approval_department",
        )
    )


def is_cleanup_document(record: BaseModel) -> TypeGuard[CleanupDocument]:
    return callable(getattr(record, "_cleanup_domain", None))


def record_as[ModelT: BaseModel](record: BaseModel, model: ModelT) -> ModelT:
    expected_type: type[ModelT] = type(model)
    if not isinstance(record, expected_type):
        raise TypeError(f"Expected {model._name}, got {record._name}.")
    return record


def model_as[ModelT: BaseModel](environment: Environment, name: str | Literal[False], model: ModelT) -> ModelT:
    return record_as(dynamic_model(environment, name), model)


@overload
def reference_as[ModelT: BaseModel](model: ModelT, xml_id: str, raise_if_not_found: Literal[True] = True) -> ModelT: ...


@overload
def reference_as[ModelT: BaseModel](
    model: ModelT, xml_id: str, raise_if_not_found: Literal[False]
) -> ModelT | None: ...


def reference_as[ModelT: BaseModel](model: ModelT, xml_id: str, raise_if_not_found: bool = True) -> ModelT | None:
    record = model.env.ref(xml_id, raise_if_not_found=raise_if_not_found)
    return record_as(record, model) if record is not None else None
