from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_CHANGE, MODEL_AUDIT_ENTRY

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
