import json
from collections import defaultdict

from lxml import etree

from odoo import api, fields, models
from odoo.fields import Command, Domain

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY, MODEL_AUDIT_MIXIN, MODEL_IR_ATTACHMENT
from odoo.addons.sol_laboratory.constants.xml_ids import AUDIT_READ_GROUP

# Odoo's bookkeeping fields and the technical path of trees say nothing about the document.
UNAUDITED_FIELDS = frozenset({"id", "create_uid", "create_date", "write_uid", "write_date", "parent_path"})
# Binary data is not text, and the documents under a one2many write their own entries.
UNAUDITED_TYPES = frozenset({"binary", "one2many"})
NUMERIC_TYPES = frozenset({"integer", "float", "monetary"})
# What a field holds before it is given a value.
EMPTY_VALUES = {"integer": 0, "float": 0.0, "monetary": 0.0}
MASK = "***"
# Tokens that open a document without signing in, such as the link a portal customer gets.
MASKED_FIELDS = frozenset({"access_token"})


def _record_text(record):
    return f"{record.display_name} (#{record.id})"


def _as_text(field, value):
    # Values are kept as text: a relation as the display name and id of the record, a date in ISO format.
    if field.type == "boolean" or field.type in NUMERIC_TYPES:
        return str(value)
    if not value:
        return None
    if field.type == "many2one":
        return _record_text(value)
    if field.type == "many2many":
        return ", ".join(_record_text(record) for record in value.sorted("id"))
    if field.type == "date":
        return fields.Date.to_string(value)
    if field.type == "datetime":
        return fields.Datetime.to_string(value)
    if field.type == "reference":
        return f"{value._name},{value.id}"
    if field.type in ("json", "properties"):
        return json.dumps(value, default=str)
    return str(value)


def _audit_value(field, value):
    # A value is compared by what it is and kept as its text: a relation is its records, so renaming a record it points
    # to does not change it.
    text = _as_text(field, value)
    if field.type in ("many2one", "many2many"):
        return (tuple(value.ids) if value else ()), text
    return text, text


# Writes an audit entry for every create, edit, archive and delete of a document.
class AuditMixin(models.AbstractModel):
    _name = MODEL_AUDIT_MIXIN
    _description = "Audit Trail"
    # Stored fields left out of the trail besides Odoo's bookkeeping fields.
    _audit_exclude = ()
    # Relations to the documents under this one, which its history includes, such as sample_ids.
    _audit_children = ()

    def _valid_field_parameter(self, field, name):
        # audit_mask=True records that a field changed without its values, for personal data.
        return name == "audit_mask" or super()._valid_field_parameter(field, name)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._audit_scope()._audit_log_creation()
        return records

    def write(self, vals):
        audited = self._audit_scope()
        before = audited._audit_values()
        result = super().write(vals)
        # A record the write brings into the trail, such as a file attached to a document, is recorded as created.
        (self._audit_scope() - audited)._audit_log_creation()
        changes = audited._audit_changes(before, audited._audit_values())
        archived = audited.filtered(
            lambda record: [change["field_name"] for change in changes[record.id]] == ["active"]
        )
        archived._audit_log("archive", changes)
        (audited - archived).filtered(lambda record: changes[record.id])._audit_log("edit", changes)
        return result

    def unlink(self):
        audited = self._audit_scope()
        names = {record.id: record.display_name for record in audited.sudo().with_context(active_test=False)}
        result = super().unlink()
        audited._audit_log("delete", notes=names)
        return result

    def _audit_scope(self):
        """The records whose actions are recorded. A model records only some of its records here."""
        return self

    def _audit_log_creation(self):
        if not self:
            return
        empty = {field.name: _audit_value(field, EMPTY_VALUES.get(field.type, False)) for field in self._audit_fields()}
        changes = self._audit_changes(dict.fromkeys(self.ids, empty), self._audit_values())
        for record_changes in changes.values():
            for change in record_changes:
                change["old_value"] = None
        self._audit_log("create", changes)

    def _audit(self, action, note=None):
        """Record an action a feature owns, such as sign, reject or download, on each record."""
        self._audit_log(action, notes=dict.fromkeys(self.ids, note))

    def _audit_log(self, action, changes=None, notes=None):
        if not self:
            return
        # Written with full rights, so people who cannot read the trail still produce entries.
        notes = notes if notes is not None else self._audit_notes()
        entries = self.env[MODEL_AUDIT_ENTRY].sudo()
        origin = entries._origin_values()
        entries.create(
            [
                {
                    **origin,
                    "action": action,
                    "document_model": self._name,
                    "document_id": document_id,
                    "note": notes.get(document_id),
                    "change_ids": [Command.create(change) for change in (changes or {}).get(document_id, [])],
                }
                for document_id in self.ids
            ]
        )

    def _audit_notes(self):
        # A model whose records are not named by their fields, such as a system parameter, says what they are here.
        return {}

    @api.model
    def _audit_fields(self):
        return [field for field in self._fields.values() if self._audit_records_field(field)]

    @api.model
    def _audit_records_field(self, field):
        if field.name in UNAUDITED_FIELDS or field.name in self._audit_exclude or field.type in UNAUDITED_TYPES:
            return False
        if field.store:
            return True
        # A field kept on another record and written through the document, delegated with _inherits or related and
        # writable, is the document's own, unless that record is audited and records it itself.
        if not (field.inherited or (field.related and not field.readonly)) or not field.related_field.base_field.store:
            return False
        return not self._audit_is_audited(self._fields[field.related.split(".")[0]].comodel_name)

    @api.model
    def _audit_is_audited(self, model_name):
        return isinstance(self.env[model_name], self.env.registry[MODEL_AUDIT_MIXIN])

    @api.model
    def _audit_relations(self):
        # The documents under this one, and the audited records it delegates fields to, which its history includes.
        delegates = [field_name for model, field_name in self._inherits.items() if self._audit_is_audited(model)]
        return (*delegates, *self._audit_children)

    def _audit_values(self):
        # Read with full rights and archived records included, so access rules never change what is recorded.
        audited = self._audit_fields()
        return {
            record.id: {field.name: _audit_value(field, record[field.name]) for field in audited}
            for record in self.sudo().with_context(active_test=False)
        }

    def _audit_changes(self, before, after):
        changes = {}
        for record in self:
            changes[record.id] = []
            for name, (new_key, new) in after[record.id].items():
                old_key, old = before[record.id][name]
                if old_key == new_key:
                    continue
                masked = record._audit_masked(name)
                changes[record.id].append(
                    {
                        "field_name": name,
                        "old_value": MASK if old is not None and masked else old,
                        "new_value": MASK if new is not None and masked else new,
                    }
                )
        return changes

    def _audit_masked(self, field_name):
        return field_name in MASKED_FIELDS or getattr(self._fields[field_name], "audit_mask", False)

    def action_open_audit_history(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("History of %s", self.display_name),
            "res_model": MODEL_AUDIT_ENTRY,
            "view_mode": "list,form",
            "domain": list(self._audit_history_domain()),
        }

    def _audit_history_domain(self):
        # The entries of the documents and, through _audit_relations, of every record under them.
        documents = defaultdict(set)
        pending = [self.sudo().with_context(active_test=False)]
        while pending:
            records = pending.pop()
            records = records.browse(set(records.ids) - documents[records._name])
            if not records:
                continue
            documents[records._name].update(records.ids)
            if self._audit_is_audited(records._name):
                pending.extend(records.mapped(relation) for relation in records._audit_relations())
        # The files attached to them, including files deleted since.
        attachments = self.env[MODEL_IR_ATTACHMENT]
        files = set().union(*(attachments._audit_files_of(model, ids) for model, ids in documents.items()))
        if files:
            documents[MODEL_IR_ATTACHMENT].update(files)
        return Domain.OR(
            Domain("document_model", "=", model) & Domain("document_id", "in", sorted(ids))
            for model, ids in documents.items()
        )

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type == "form":
            self._add_history_button(arch)
        return arch, view

    @api.model
    def _add_history_button(self, arch):
        # A form without a sheet gets the button box at its top, below its header.
        container = arch.find(".//sheet")
        if container is None:
            container = arch
        button_box = container.find(".//div[@name='button_box']")
        if button_box is None:
            button_box = etree.Element("div", {"class": "oe_button_box", "name": "button_box"})
            header = container.find("header")
            container.insert(0 if header is None else container.index(header) + 1, button_box)
        button_box.append(
            etree.Element(
                "button",
                {
                    "name": "action_open_audit_history",
                    "type": "object",
                    "class": "oe_stat_button",
                    "icon": "fa-history",
                    "string": self.env._("History"),
                    "groups": AUDIT_READ_GROUP,
                    "invisible": "not id",
                },
            )
        )
