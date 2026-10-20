import hashlib

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_datetime

from odoo.addons.base.models.ir_model import MODULE_UNINSTALL_FLAG
from odoo.addons.sol_laboratory.constants.approvals import DECISION_SIGNED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DIGITAL_SIGNATURE,
    MODEL_IR_ATTACHMENT,
    MODEL_PERMISSION_MIXIN,
    MODEL_SIGNATURE,
    MODEL_SIGNING_CERTIFICATE,
)
from odoo.addons.sol_laboratory.services.pdf_signing import check_pdf


# Chữ Ký Số
class DigitalSignature(models.Model):
    _name = MODEL_DIGITAL_SIGNATURE
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Digital Signature"
    _order = "id desc"
    # Printing a fully signed document makes its digital signature; it is never edited or deleted on the screen.
    _permission_actions = ("read",)

    # Technical name of the model of the signed document, such as medilab.test.report.
    document_model = fields.Char(string="Document Type", required=True, readonly=True)
    # Id of the signed document.
    document_id = fields.Integer(string="Document ID", required=True, readonly=True)
    # Name of the signed document.
    document_name = fields.Char(string="Document", compute="_compute_document_name")
    # Version of the document whose PDF was signed.
    document_version = fields.Integer(required=True, readonly=True)
    # The laboratory's certificate Viettel Sign signed with.
    certificate_id = fields.Many2one(
        MODEL_SIGNING_CERTIFICATE, string="Certificate", required=True, readonly=True, ondelete="restrict"
    )
    # The PDF Viettel Sign signed, returned on every download.
    attachment_id = fields.Many2one(
        MODEL_IR_ATTACHMENT, string="Signed PDF", required=True, readonly=True, ondelete="restrict"
    )
    # When Viettel Sign signed the PDF.
    signed_at = fields.Datetime(required=True, readonly=True)
    # SHA-256 of the signed PDF, which finds it when someone verifies a file.
    file_hash = fields.Char(string="SHA-256", required=True, readonly=True)

    _version_unique = models.Constraint(
        "UNIQUE(document_model, document_id, document_version)", "A document version is digitally signed once."
    )
    _file_hash_unique = models.Constraint("UNIQUE(file_hash)", "This signed PDF is already stored.")

    @api.depends("certificate_id.name", "signed_at")
    def _compute_display_name(self):
        for signature in self:
            signature.display_name = self.env._(
                "Signed with %(certificate)s on %(time)s",
                certificate=signature.certificate_id.name,
                time=format_datetime(self.env, signature.signed_at),
            )

    @api.depends("document_model", "document_id")
    def _compute_document_name(self):
        for signature in self:
            document = signature._document()
            signature.document_name = document.display_name if document else signature.document_model

    def action_download(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{self.attachment_id.id}?download=true",
            "target": "self",
        }

    def unlink(self):
        # Only uninstalling the module removes digital signatures.
        if not self.env.context.get(MODULE_UNINSTALL_FLAG):
            raise UserError(self.env._("A digital signature cannot be deleted."))
        return super().unlink()

    def _document(self):
        self.ensure_one()
        if self.document_model not in self.env:
            return None
        return self.env[self.document_model].sudo().browse(self.document_id).exists() or None

    def _approvals(self):
        """The signatures of the document's approval chain that stand on the signed version, in signing order."""
        self.ensure_one()
        return (
            self.env[MODEL_SIGNATURE]
            .sudo()
            .search(
                [
                    ("document_model", "=", self.document_model),
                    ("document_id", "=", self.document_id),
                    ("document_version", "=", self.document_version),
                    ("decision", "=", DECISION_SIGNED),
                    ("withdrawn_at", "=", False),
                ],
                order="id",
            )
        )

    @api.model
    def _verify_file(self, data):
        """What the verification page shows for an uploaded file: whether it is signed, each check, and for a valid file
        its digital signature."""
        check = check_pdf(data)
        if check is None:
            return {"signed": False, "valid": False}
        signature = self.sudo().search([("file_hash", "=", hashlib.sha256(data).hexdigest())], limit=1)
        result = {
            "signed": True,
            "signature_valid": check.signature_valid,
            "laboratory_certificate": bool(self.env[MODEL_SIGNING_CERTIFICATE]._of_certificate(check.certificate)),
            "unchanged": check.whole_file and bool(signature),
        }
        result["valid"] = all(result.values())
        result["signature"] = signature if result["valid"] else self.browse()
        return result
