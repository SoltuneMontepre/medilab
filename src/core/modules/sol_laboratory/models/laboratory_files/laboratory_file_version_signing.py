from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.approvals import (
    STATE_APPROVED,
    STATE_NONE,
    STATE_REJECTED,
    STATE_REQUESTED,
)
from odoo.addons.sol_laboratory.constants.laboratory_files import FILE_READ, RESULT
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_APPROVAL_MIXIN,
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_MAIL_MESSAGE,
    MODEL_SIGNATURE,
)
from odoo.addons.sol_laboratory.constants.notifications import EVENT_LABORATORY_FILE_VERSION_REJECTED


# Phiên Bản Tệp: a version of a result file is signed through the approval chain of laboratory file versions.
class LaboratoryFileVersionSigning(models.Model):
    _name = MODEL_LABORATORY_FILE_VERSION
    # The version inherits the audit mixin already, so the approval mixin, which inherits it too, comes first.
    _inherit = [MODEL_APPROVAL_MIXIN, MODEL_LABORATORY_FILE_VERSION]
    _permission_actions = ("read", "sign")

    # Where the version is in its signing; only signing, rejecting and withdrawing set it.
    approval_state = fields.Selection(
        [
            (STATE_NONE, "Not Signed"),
            (STATE_REQUESTED, "Being Signed"),
            (STATE_APPROVED, "Signed"),
            (STATE_REJECTED, "Rejected"),
        ],
        string="Signing",
        required=True,
        default=STATE_NONE,
        readonly=True,
        copy=False,
    )
    # The signatures and rejections given on the version, withdrawn ones included.
    signature_ids = fields.Many2many(MODEL_SIGNATURE, compute="_compute_signature_ids", string="Signatures")

    def _compute_signature_ids(self):
        # The form lists them only to people who read signatures.
        signatures = (
            self.env[MODEL_SIGNATURE]
            .sudo()
            .search([("document_model", "=", self._name), ("document_id", "in", self.ids)])
        )
        by_version = signatures.grouped("document_id")
        for version in self:
            version.signature_ids = by_version.get(version.id, signatures.browse()).with_env(self.env)

    def write(self, vals):
        if "approval_state" in vals and not self.env.su:
            raise UserError(self.env._("A version's signing state changes only by signing, rejecting or withdrawing."))
        return super().write(vals)

    def action_sign(self):
        self.ensure_one()
        # The signer is checked before the file's row is taken, so someone who may not sign never waits on a save.
        self._approval_check_actor()
        self.sudo().file_id._lock_for_signing()
        return super().action_sign()

    def action_reject(self, reason):
        self.ensure_one()
        self._approval_check_actor(rejecting=True)
        self.sudo().file_id._lock_for_signing()
        return super().action_reject(reason)

    def action_withdraw(self):
        self.ensure_one()
        self._check_withdrawing_access()
        return super().action_withdraw()

    def _approval_check_withdraw(self):
        self._check_withdrawing_access()
        return super()._approval_check_withdraw()

    def _check_withdrawing_access(self):
        # Withdrawing writes with full rights, so only a signer who still reads the version's file withdraws.
        self.sudo().file_id.with_env(self.env)._check_file_access(FILE_READ)

    def _approval_check_actor(self, rejecting=False):
        """Only the current version of a file in a result folder is signed or rejected, by a member of the folder who
        sees its sample, at the level of the chain their role signs."""
        self.ensure_one()
        # The file is reached with full rights and checked as the person, so the refusal is always not_found.
        self.sudo().file_id.with_env(self.env)._check_file_access(FILE_READ)
        version = self.sudo()
        if version.file_id.folder_id.category != RESULT:
            raise UserError(self.env._("Only versions of the files of a result folder are signed."))
        if version.file_id.current_version_id != version:
            raise UserError(self.env._("Only the current version of a file is signed; this one has a newer version."))
        return super()._approval_check_actor(rejecting)

    def _approval_document_hash(self):
        return self.sha256

    def _approval_set_state(self, state):
        self.approval_state = state

    def _approval_notify_rejected(self, reason):
        self.ensure_one()
        # A version can be rejected again once its rejection is withdrawn, so each round is told once.
        self.env[MODEL_MAIL_MESSAGE].raise_event(
            EVENT_LABORATORY_FILE_VERSION_REJECTED,
            self,
            f"laboratory_file_version:{self.id}:{self.document_version}:rejected",
            self.env._("%(version)s was rejected: %(reason)s", version=self.display_name, reason=reason),
            subject=self.display_name,
            partners=self.sudo().user_id.partner_id,
        )
