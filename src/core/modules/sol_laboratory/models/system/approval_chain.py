from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_list

from odoo.addons.sol_laboratory.constants.approvals import PURPOSE_CHANGE_REQUEST, PURPOSE_SIGNING
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_APPROVAL_CHAIN,
    MODEL_APPROVAL_LEVEL,
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_SIGNATURE,
)


# Chuỗi Phê Duyệt
class ApprovalChain(models.Model):
    _name = MODEL_APPROVAL_CHAIN
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Approval Chain"
    _order = "document_model, purpose"
    _permission_actions = ("read", "create", "edit", "archive", "delete")
    _audit_children = ("level_ids",)

    # Technical name of the model of the document the chain signs, such as medilab.test.result.
    document_model = fields.Char(string="Document Type", required=True)
    # Whether the chain signs the document itself or the change requests on it.
    purpose = fields.Selection(
        [(PURPOSE_SIGNING, "Signing"), (PURPOSE_CHANGE_REQUEST, "Change request")], required=True
    )
    # Chain name in each language.
    name = fields.Char(required=True, translate=True)
    # False when the chain is archived.
    active = fields.Boolean(default=True)
    # Levels of the chain, in signing order.
    level_ids = fields.One2many(MODEL_APPROVAL_LEVEL, "chain_id", string="Levels")

    _purpose_unique = models.Constraint(
        "UNIQUE(document_model, purpose)", "A document type cannot have two chains for the same purpose."
    )

    @api.ondelete(at_uninstall=False)
    def _unlink_except_signed(self):
        signatures = self.env[MODEL_SIGNATURE].sudo().search([("level_id.chain_id", "in", self.ids)])
        if signatures:
            raise UserError(
                self.env._(
                    "A chain with signatures cannot be deleted; archive it instead. Signatures: %s",
                    format_list(self.env, signatures.mapped("display_name")),
                )
            )
