from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_list

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_APPROVAL_CHAIN,
    MODEL_APPROVAL_LEVEL,
    MODEL_PERMISSION_MIXIN,
    MODEL_ROLE,
    MODEL_SIGNATURE,
)


# Cấp Phê Duyệt
class ApprovalLevel(models.Model):
    _name = MODEL_APPROVAL_LEVEL
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Approval Level"
    _order = "chain_id, sequence"
    _permission_actions = ("read", "create", "edit", "delete")

    # The chain the level belongs to.
    chain_id = fields.Many2one(MODEL_APPROVAL_CHAIN, string="Chain", required=True, ondelete="cascade")
    # Position in the chain; lower levels sign first.
    sequence = fields.Integer(required=True)
    # Level name in each language, such as "Head of department".
    name = fields.Char(required=True, translate=True)
    # The role a person needs to sign at this level.
    role_id = fields.Many2one(MODEL_ROLE, string="Role", required=True, ondelete="restrict")
    # True when the signer must belong to the department that did the work.
    same_department = fields.Boolean()
    # True when the signer may reject instead of signing.
    can_reject = fields.Boolean(default=True)

    _sequence_unique = models.Constraint(
        "UNIQUE(chain_id, sequence)", "A chain cannot have two levels in the same position."
    )

    @api.ondelete(at_uninstall=False)
    def _unlink_except_signed(self):
        signatures = self.env[MODEL_SIGNATURE].sudo().search([("level_id", "in", self.ids)])
        if signatures:
            raise UserError(
                self.env._(
                    "A level with signatures cannot be deleted. Signatures: %s",
                    format_list(self.env, signatures.mapped("display_name")),
                )
            )
