import hashlib

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.approvals import DECISION_SIGNED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_APPROVAL_MIXIN,
    MODEL_DIGITAL_SIGNATURE,
    MODEL_DIGITAL_SIGNING_MIXIN,
    MODEL_IR_ACTIONS_REPORT,
    MODEL_IR_ATTACHMENT,
    MODEL_JOB_ITEM,
    MODEL_RES_CONFIG_SETTINGS,
    MODEL_SCHEDULED_JOB,
    MODEL_SIGNING_CERTIFICATE,
)
from odoo.addons.sol_laboratory.constants.signing import DIGITAL_SIGNING_JOB, UNSIGNED_PRINT_CONTEXT
from odoo.addons.sol_laboratory.services.pdf_signing import certificate_chain, check_pdf, sign_pdf
from odoo.addons.sol_laboratory.services.viettel_sign_client import ViettelSignError, viettel_sign_client

# Statuses of a signing job item that still waits: to be tried, being tried, or given up until someone retries it.
QUEUED_STATUSES = ("pending", "running", "failed")


# Ký số: a fully signed document prints as the PDF Viettel Sign signed.
class DigitalSigningMixin(models.AbstractModel):
    _name = MODEL_DIGITAL_SIGNING_MIXIN
    # Only a document signed through an approval chain is digitally signed.
    _inherit = [MODEL_APPROVAL_MIXIN]
    _description = "Digital Signing"
    # External id of the report whose PDF Viettel Sign signs once the document is fully signed.
    _digital_signing_report = None

    # The digital signature of the document's current version; empty until Viettel Sign signed its PDF.
    digital_signature_id = fields.Many2one(
        MODEL_DIGITAL_SIGNATURE, compute="_compute_digital_signature", compute_sudo=True, store=True, index=True
    )
    # When Viettel Sign signed the PDF of the current version.
    digital_signed_at = fields.Datetime(related="digital_signature_id.signed_at", string="Digitally Signed At")
    # True when the signing of the document's PDF waits in the signing job's queue.
    digital_signing_pending = fields.Boolean(compute="_compute_digital_signing_pending", compute_sudo=True)

    @api.depends("document_version")
    def _compute_digital_signature(self):
        signatures = (
            self.env[MODEL_DIGITAL_SIGNATURE]
            .sudo()
            .search([("document_model", "=", self._name), ("document_id", "in", self.ids)])
        )
        for document in self:
            document.digital_signature_id = signatures.filtered(
                lambda signature, document=document: (
                    signature.document_id == document.id and signature.document_version == document.document_version
                )
            )[:1]

    # A stored field and a non-stored field cannot share a compute; the registry warns when they do.
    @api.depends("digital_signature_id", "document_version")
    def _compute_digital_signing_pending(self):
        queued = set(
            self.env[MODEL_JOB_ITEM]
            .sudo()
            .search(
                [
                    ("job_id.key", "=", DIGITAL_SIGNING_JOB),
                    ("document_model", "=", self._name),
                    ("document_id", "in", self.ids),
                    ("status", "in", QUEUED_STATUSES),
                ]
            )
            .mapped("item_key")
        )
        enabled = self._digital_signing_enabled()
        for document in self:
            document.digital_signing_pending = bool(
                enabled
                and document.id
                and not document.digital_signature_id
                and document._digital_signing_key() in queued
            )

    @api.model
    def _digital_signing_enabled(self):
        return self.env[MODEL_RES_CONFIG_SETTINGS]._get_parameter("digital_signing_enabled")

    def _digital_signing_fully_signed(self):
        """True when every level of the document's chain stands signed; a host that keeps its own status says it from
        there."""
        self.ensure_one()
        levels = self._approval_chain().level_ids
        signed = self._approval_open_rows().filtered(lambda row: row.decision == DECISION_SIGNED)
        return bool(levels) and not (levels - signed.level_id)

    def _digital_signing_draft(self):
        """True when the document prints as a marked draft: it is still under approval."""
        self.ensure_one()
        return not self._digital_signing_fully_signed()

    def _digital_signing_filename(self):
        self.ensure_one()
        return f"{self.display_name}.pdf"

    def _digital_signing_key(self):
        self.ensure_one()
        return f"{self._name}:{self.id}:{self.document_version}"

    def _digital_signing_start(self):
        """Sign the PDF of each fully signed document now. When Viettel Sign fails, the approval stands: the signing is
        queued for the signing job and the user is told."""
        for document in self.sudo():
            try:
                with self.env.cr.savepoint():
                    document._digital_sign()
            except ViettelSignError as error:
                document._audit("error", self.env._("Viettel Sign did not sign the PDF: %s", error))
                self.env[MODEL_SCHEDULED_JOB].queue(
                    DIGITAL_SIGNING_JOB, document._digital_signing_key(), document=document
                )
                document.invalidate_recordset(["digital_signing_pending"])
                self.env.user._bus_send(
                    "simple_notification",
                    {
                        "type": "warning",
                        "sticky": True,
                        "message": self.env._(
                            "%s is approved, but Viettel Sign could not sign its PDF. It is retried automatically.",
                            document.display_name,
                        ),
                    },
                )

    def action_retry_digital_signing(self):
        self.ensure_one()
        self.check_access("read")
        if not self.digital_signing_pending:
            raise UserError(self.env._("%s has no PDF waiting for its digital signature.", self.display_name))
        try:
            self.sudo()._digital_sign()
        except ViettelSignError as error:
            raise UserError(self.env._("Viettel Sign could not sign the PDF. It is retried automatically.")) from error
        return True

    def _digital_signed_pdf(self):
        """The digitally signed PDF of the fully signed document, signed now when it has none yet."""
        self.ensure_one()
        try:
            signature = self.sudo()._digital_sign()
        except ViettelSignError as error:
            raise UserError(
                self.env._(
                    "Viettel Sign could not sign the PDF of %s. It is retried automatically; print it again later.",
                    self.display_name,
                )
            ) from error
        return bytes(signature.attachment_id.raw)

    def _digital_sign(self):
        """Have Viettel Sign sign the PDF of the document's current version, store it and return its digital signature;
        a version already signed returns the one it has."""
        self.ensure_one()
        if self.digital_signature_id:
            return self.digital_signature_id
        client = viettel_sign_client()
        certificate = self.env[MODEL_SIGNING_CERTIFICATE]._signing()
        pdf, _report_type = (
            self.env[MODEL_IR_ACTIONS_REPORT]
            .with_context(**{UNSIGNED_PRINT_CONTEXT: True})
            ._render_qweb_pdf(self._digital_signing_report, self.ids)
        )
        chain = certificate_chain(certificate.certificate_chain)
        signed = sign_pdf(
            pdf, chain, lambda digest: client.sign_hash(certificate.credential_id, digest, self.display_name)
        )
        check = check_pdf(signed)
        if not (check and check.signature_valid and check.certificate == chain[0]):
            raise ViettelSignError(
                f"Viettel Sign returned a signature the certificate {certificate.name} does not verify"
            )
        return self._digital_signing_store(signed, certificate)

    def _digital_signing_store(self, pdf, certificate):
        """Store the PDF Viettel Sign signed with the certificate as the document's digital signature."""
        self.ensure_one()
        attachment = (
            self.env[MODEL_IR_ATTACHMENT]
            .sudo()
            .create(
                {
                    "name": self._digital_signing_filename(),
                    "raw": pdf,
                    "mimetype": "application/pdf",
                    "res_model": self._name,
                    "res_id": self.id,
                }
            )
        )
        signature = (
            self.env[MODEL_DIGITAL_SIGNATURE]
            .sudo()
            .create(
                {
                    "document_model": self._name,
                    "document_id": self.id,
                    "document_version": self.document_version,
                    "certificate_id": certificate.id,
                    "attachment_id": attachment.id,
                    "signed_at": fields.Datetime.now(),
                    "file_hash": hashlib.sha256(pdf).hexdigest(),
                }
            )
        )
        self._audit("integration", self.env._("Viettel Sign signed the PDF with the certificate %s", certificate.name))
        self.invalidate_recordset(["digital_signature_id", "digital_signing_pending"])
        self._digital_signing_done(signature)
        return signature

    def _digital_signing_done(self, signature):
        # Called once Viettel Sign signed the PDF; hosts use the signed file here, such as to deliver it.
        pass
