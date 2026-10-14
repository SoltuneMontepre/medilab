from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import SQL

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_CHANGE, MODEL_AUDIT_ENTRY, MODEL_AUDIT_MIXIN
from odoo.addons.sol_laboratory.models.mixins.audit_mixin import mask_text

NO_VALUE = "—"


# Thay Đổi Dữ Liệu
class AuditChange(models.Model):
    _name = MODEL_AUDIT_CHANGE
    _description = "Audit Change"
    _order = "entry_id, id"

    # The audit entry the change belongs to.
    entry_id = fields.Many2one(MODEL_AUDIT_ENTRY, required=True, readonly=True, ondelete="restrict", index=True)
    # Technical name of the field changed.
    field_name = fields.Char(required=True, readonly=True)
    # Value before the change, as text.
    old_value = fields.Text(readonly=True)
    # Value after the change, as text.
    new_value = fields.Text(readonly=True)
    # Label of the field changed, in the reader's language.
    field_label = fields.Char(string="Field", compute="_compute_field_label")

    @api.depends("entry_id.document_model", "field_name")
    def _compute_field_label(self):
        for change in self:
            model = change.entry_id.document_model
            field = self.env[model]._fields.get(change.field_name) if model in self.env else None
            change.field_label = field._description_string(self.env) if field else change.field_name

    @api.depends("field_label", "old_value", "new_value")
    def _compute_display_name(self):
        for change in self:
            change.display_name = (
                f"{change.field_label}: {change.old_value or NO_VALUE} → {change.new_value or NO_VALUE}"
            )

    def write(self, vals):
        self._refuse_change()
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_audit_change(self):
        raise UserError(self.env._("Audit changes cannot be deleted."))

    def _refuse_change(self):
        raise UserError(self.env._("Audit changes cannot be changed."))

    @api.model
    def _mask_recorded_values(self):
        """Mask the values recorded before their field was masked, as the field is masked now. Changes refuse every
        write, so the upgrade that masks them writes the table directly."""
        entries = self.env[MODEL_AUDIT_ENTRY]
        tables = {"change": SQL.identifier(self._table), "entry": SQL.identifier(entries._table)}
        self.env.cr.execute(
            SQL(
                "SELECT DISTINCT entry.document_model, change.field_name "
                "FROM %(change)s change JOIN %(entry)s entry ON entry.id = change.entry_id",
                **tables,
            )
        )
        mixin = self.env.registry[MODEL_AUDIT_MIXIN]
        for model_name, field_name in self.env.cr.fetchall():
            documents = self.env.get(model_name)
            if not isinstance(documents, mixin) or field_name not in documents._fields:
                continue
            kind = documents._audit_mask(field_name)
            if not kind:
                continue
            field_type = documents._fields[field_name].type
            self.env.cr.execute(
                SQL(
                    "SELECT change.id, change.old_value, change.new_value "
                    "FROM %(change)s change JOIN %(entry)s entry ON entry.id = change.entry_id "
                    "WHERE entry.document_model = %(model)s AND change.field_name = %(field)s",
                    model=model_name,
                    field=field_name,
                    **tables,
                )
            )
            for change_id, old, new in self.env.cr.fetchall():
                masked = (mask_text(kind, field_type, old), mask_text(kind, field_type, new))
                if masked != (old, new):
                    self.env.cr.execute(
                        SQL(
                            "UPDATE %(change)s SET old_value = %(old)s, new_value = %(new)s WHERE id = %(id)s",
                            change=tables["change"],
                            old=masked[0],
                            new=masked[1],
                            id=change_id,
                        )
                    )
