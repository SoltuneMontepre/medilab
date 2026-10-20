from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LABORATORY_FOLDER,
    MODEL_LABORATORY_SYNC_RULE,
    MODEL_LOCK_MIXIN,
    MODEL_PERMISSION_MIXIN,
)


# Quy Tắc Đồng Bộ
class LaboratorySyncRule(models.Model):
    _name = MODEL_LABORATORY_SYNC_RULE
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Laboratory Sync Rule"
    _order = "folder_id, id"
    _rec_name = "pattern"
    # A rule that is no longer wanted is removed or turned off.
    _permission_actions = ("read", "create", "edit", "delete")

    # The folder the rule limits.
    folder_id = fields.Many2one(MODEL_LABORATORY_FOLDER, string="Folder", required=True, ondelete="cascade", index=True)
    # prefix, glob or extension.
    kind = fields.Selection(
        [("prefix", "Name Prefix"), ("glob", "Name Pattern"), ("extension", "Extension")],
        required=True,
        default="prefix",
    )
    # The name prefix, pattern with * or extension the file must match.
    pattern = fields.Char(required=True)
    # True when files in subfolders count too.
    recursive = fields.Boolean(string="Include Subfolders", default=True)
    # False when the rule is turned off.
    enabled = fields.Boolean(default=True)
