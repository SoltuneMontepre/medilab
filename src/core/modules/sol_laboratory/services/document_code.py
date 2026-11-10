"""The code a push and Medilab Mobile name a document by."""

from odoo.models import BaseModel


def document_code(record: BaseModel) -> str:
    """The document's own code, such as a sample's lab code, or the code its model gives through _document_code(), such
    as its sample's lab code for a sample test; empty when it has none. Read with full rights: a code names no customer,
    and a push names it to people who may no longer read the document."""
    record = record.sudo().exists()
    if not record:
        return ""
    own = getattr(record, "_document_code", None)
    if callable(own):
        return str(own() or "")
    field = record._fields.get("code")
    if field is None or field.type != "char":
        return ""
    return str(record["code"] or "")
