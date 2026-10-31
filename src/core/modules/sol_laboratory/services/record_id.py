"""Require database identifiers when building commands that link persisted records."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from odoo.models import BaseModel


def persisted_id(record: "BaseModel") -> int:
    value = record.id
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    raise ValueError("A persisted record with a positive database ID is required.")


def persisted_ids(records: "BaseModel") -> list[int]:
    return [persisted_id(record) for record in records]
