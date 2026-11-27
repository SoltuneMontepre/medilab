from contextvars import ContextVar
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.approvals import DECISION_REJECTED, DECISION_SIGNED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_APPROVAL_LEVEL,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_SIGNATURE,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_signature as SignatureBase
else:
    SignatureBase = object

# Only the private withdrawal action authorizes writing its timestamp, never an RPC context key.
WITHDRAWING_SIGNATURE_IDS = ContextVar("medilab_withdrawing_signature_ids", default=frozenset())


# Chữ Ký
class Signature(models.Model, SignatureBase):
    _name = MODEL_SIGNATURE
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Signature"
    _order = "id"
    # Signatures are given through the approval mixin and never edited or deleted on the screen.
    _permission_actions = ("read",)

    if not TYPE_CHECKING:
        # Technical name of the model of the signed document, such as medilab.test.result.
        document_model = fields.Char(string="Document Type", required=True)
        # Id of the signed document.
        document_id = fields.Integer(string="Document", required=True)
        # Version of the document that was signed.
        document_version = fields.Integer(required=True, default=1)
        # SHA-256 of the content signed, for a document type whose content has one, such as a laboratory file version.
        document_hash = fields.Char(string="Document Hash")
        # The level signed at.
        level_id = fields.Many2one(MODEL_APPROVAL_LEVEL, string="Level", required=True, ondelete="restrict")
        # The person who signed; empty for a subcontractor's person, who signs in to the portal and is no person of the
        # laboratory.
        signer_id = fields.Many2one(MODEL_PERSON, string="Signer", ondelete="restrict")
        # Name of the signer at the time of signing.
        signer_name = fields.Char(required=True)
        # Name of the role the signer signed with at the time: the level's own, or a later level's that signed it in
        # the signer's own name.
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
            if signature.decision == DECISION_REJECTED and not ((signature.reason or "").strip()):
                raise ValidationError(self.env._("A rejection needs a reason."))

    @api.depends("signer_name", "level_name")
    def _compute_display_name(self):
        for signature in self:
            signature.display_name = f"{signature.signer_name} - {signature.level_name}"

    @api.model_create_multi
    def create(self, vals_list):
        # A signature is given in force, whatever default the context carries.
        for vals in vals_list:
            if vals.get("withdrawn_at"):
                raise UserError(self.env._("A signature is given in force; only withdrawing it records a withdrawal."))
            vals["withdrawn_at"] = False
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su or vals.keys() != {"withdrawn_at"} or not set(self.ids) <= WITHDRAWING_SIGNATURE_IDS.get():
            raise UserError(self.env._("A signature cannot be changed once it is given."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_on_uninstall(self):
        raise UserError(self.env._("A signature is withdrawn, not deleted."))

    @api.model
    def _in_use_domain(self):
        # A signature stays in the record whoever signed it, so it never stops its signer from being archived.
        return Domain.FALSE

    def _withdraw(self, process_completed=False):
        for signature in self:
            signature._check_withdrawable(process_completed)
        self._record_withdrawal()

    def _record_withdrawal(self):
        signatures = self.sudo()
        if signatures.filtered("withdrawn_at"):
            raise UserError(self.env._("This signature is already withdrawn."))
        token = WITHDRAWING_SIGNATURE_IDS.set(frozenset(signatures.ids))
        try:
            signatures.withdrawn_at = fields.Datetime.now()
        finally:
            WITHDRAWING_SIGNATURE_IDS.reset(token)

    def _check_withdrawable(self, process_completed=False):
        self.ensure_one()
        signature = self.sudo()
        if not signature.signer_id or signature.signer_id != self.env[MODEL_PERSON]._current():
            raise UserError(self.env._("Only the person who signed can withdraw a signature."))
        if signature.withdrawn_at:
            raise UserError(self.env._("This signature is already withdrawn."))
        if process_completed:
            raise UserError(self.env._("The process of the document is completed, so a signature cannot be withdrawn."))
        if signature._later_rows():
            raise UserError(self.env._("Withdraw the signatures given after yours first."))

    def _later_rows(self):
        # Rows of the same document given after this one that are not withdrawn; a rejection counts. The id grows with
        # every row, so it orders them where the creation time can be equal.
        self.ensure_one()
        return self.search(
            [
                ("document_model", "=", self.document_model),
                ("document_id", "=", self.document_id),
                ("withdrawn_at", "=", False),
                ("id", ">", self.id),
            ]
        )
