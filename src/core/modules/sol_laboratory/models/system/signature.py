from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain

from odoo.addons.base.models.ir_model import MODULE_UNINSTALL_FLAG
from odoo.addons.sol_laboratory.constants.approvals import DECISION_REJECTED, DECISION_SIGNED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_APPROVAL_LEVEL,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_SIGNATURE,
)


# Chữ Ký
class Signature(models.Model):
    _name = MODEL_SIGNATURE
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Signature"
    _order = "id"
    # Signatures are given through the approval mixin and never edited or deleted on the screen.
    _permission_actions = ("read",)

    # Technical name of the model of the signed document, such as sale.order.
    document_model = fields.Char(string="Document Type", required=True)
    # Id of the signed document.
    document_id = fields.Integer(string="Document", required=True)
    # Version of the document that was signed.
    document_version = fields.Integer(required=True, default=1)
    # SHA-256 of the content signed, for a document type whose content has one, such as a laboratory file version.
    document_hash = fields.Char(string="Document Hash")
    # The level signed at.
    level_id = fields.Many2one(MODEL_APPROVAL_LEVEL, string="Level", required=True, ondelete="restrict")
    # The person who signed.
    signer_id = fields.Many2one(MODEL_PERSON, string="Signer", required=True, ondelete="restrict")
    # Name of the signer at the time of signing.
    signer_name = fields.Char(required=True)
    # Name of the signer's role at the time of signing.
    signer_role = fields.Char(required=True)
    # Name of the level at the time of signing.
    level_name = fields.Char(required=True)
    # Whether the signer signed or rejected the document.
    decision = fields.Selection([(DECISION_SIGNED, "Signed"), (DECISION_REJECTED, "Rejected")], required=True)
    # Reason the signer gave for a rejection.
    reason = fields.Text()
    # When the signer withdrew the signature; empty while it stands.
    withdrawn_at = fields.Datetime()

    _document_idx = models.Index("(document_model, document_id)")

    @api.constrains("decision", "reason")
    def _check_rejection_reason(self):
        for signature in self:
            if signature.decision == DECISION_REJECTED and not (signature.reason or "").strip():
                raise ValidationError(self.env._("A rejection needs a reason."))

    @api.depends("signer_name", "level_name")
    def _compute_display_name(self):
        for signature in self:
            signature.display_name = f"{signature.signer_name} - {signature.level_name}"

    def unlink(self):
        # Only uninstalling the module removes signatures.
        if not self.env.context.get(MODULE_UNINSTALL_FLAG):
            raise UserError(self.env._("A signature is withdrawn, not deleted."))
        return super().unlink()

    @api.model
    def _in_use_domain(self):
        # A signature stays in the record whoever signed it, so it never stops its signer from being archived.
        return Domain.FALSE

    def _withdraw(self, process_completed=False):
        for signature in self:
            signature._check_withdrawable(process_completed)
        self.sudo().write({"withdrawn_at": fields.Datetime.now()})

    def _check_withdrawable(self, process_completed=False):
        self.ensure_one()
        signature = self.sudo()
        if signature.signer_id != self.env[MODEL_PERSON]._current():
            raise UserError(self.env._("Only the person who signed can withdraw a signature."))
        if signature.withdrawn_at:
            raise UserError(self.env._("This signature is already withdrawn."))
        if process_completed:
            raise UserError(self.env._("The process of the document is completed, so a signature cannot be withdrawn."))
        if signature._higher_rows():
            raise UserError(self.env._("Withdraw the signatures of the higher levels first."))

    def _higher_rows(self):
        # Rows of higher levels of the same chain on the same document that are not withdrawn; a rejection counts.
        self.ensure_one()
        return self.search(
            [
                ("document_model", "=", self.document_model),
                ("document_id", "=", self.document_id),
                ("withdrawn_at", "=", False),
                ("level_id.chain_id", "=", self.level_id.chain_id.id),
                ("level_id.sequence", ">", self.level_id.sequence),
            ]
        )
