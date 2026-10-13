from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_CODE_MIXIN,
    MODEL_HANDOVER_RECORD,
    MODEL_HANDOVER_RECORD_SAMPLE,
    MODEL_MOBILE_DEVICE,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_TEST_REQUEST,
)
from odoo.addons.sol_laboratory.constants.notifications import EVENT_HANDOVER_RECORD_SIGNED
from odoo.addons.sol_laboratory.constants.xml_ids import HANDOVER_RECORD_REPORT


# Biên Bản Giao Nhận Mẫu
class HandoverRecord(models.Model):
    _name = MODEL_HANDOVER_RECORD
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_CODE_MIXIN]
    _description = "Handover Record"
    _order = "handed_over_at desc, id desc"
    _rec_name = "code"
    # A signed record is never edited or deleted; a correction is a new record.
    _permission_actions = ("read", "create", "edit")

    # Unique code of the record, such as BBGN.2026.0001; filled from a sequence when left empty.
    code = fields.Char(required=True, copy=False, readonly=True)
    # The test request whose samples are handed over.
    request_id = fields.Many2one(
        MODEL_TEST_REQUEST, string="Test Request", required=True, ondelete="restrict", index=True
    )
    # When the samples were handed over.
    handed_over_at = fields.Datetime(required=True, default=fields.Datetime.now)
    # Name of the customer's person who handed the samples over and signed.
    handed_over_by_name = fields.Char(string="Handed Over By", required=True)
    # Sample delivery staff who took the samples.
    received_by_id = fields.Many2one(MODEL_PERSON, string="Received By", required=True, ondelete="restrict")
    # Whether the customer has signed: draft or signed.
    status = fields.Selection(
        [("draft", "Draft"), ("signed", "Signed")], required=True, default="draft", readonly=True, copy=False
    )
    # When the customer signed.
    signed_at = fields.Datetime(readonly=True, copy=False)
    # Image of the customer's handwritten signature.
    signature_attachment_id = fields.Many2one(
        "ir.attachment", string="Signature", readonly=True, copy=False, ondelete="restrict"
    )
    # The mobile device the customer signed on.
    signed_device_id = fields.Many2one(
        MODEL_MOBILE_DEVICE, string="Signed on Device", readonly=True, copy=False, ondelete="set null"
    )
    # The record's PDF.
    attachment_id = fields.Many2one("ir.attachment", string="PDF", readonly=True, copy=False, ondelete="restrict")
    # When the PDF was emailed to the customer.
    sent_at = fields.Datetime(readonly=True, copy=False)
    # Samples on the record, with the amount and condition handed over.
    sample_ids = fields.One2many(MODEL_HANDOVER_RECORD_SAMPLE, "record_id", string="Samples")

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a handover record must be unique.")

    def write(self, vals):
        if any(record.status == "signed" for record in self):
            raise UserError(self.env._("A signed handover record cannot be changed. Create a new record instead."))
        return super().write(vals)

    def unlink(self):
        if any(record.status == "signed" for record in self):
            raise UserError(self.env._("A signed handover record cannot be deleted."))
        return super().unlink()

    def action_sign(self, signature, device_id=None):
        """The mobile app sends the customer's handwritten signature as PNG bytes and the device it was signed on."""
        for record in self:
            record._sign(signature, device_id)

    def _sign(self, signature, device_id):
        self.ensure_one()
        if self.status != "draft":
            raise UserError(self.env._("A signed handover record cannot be changed. Create a new record instead."))
        if not self.sample_ids:
            raise UserError(self.env._("Add the samples to handover record %s before signing it.", self.code))
        attachments = self.env["ir.attachment"]
        signature_attachment = attachments.create(
            {"name": f"{self.code}-signature.png", "raw": signature, "res_model": self._name, "res_id": self.id}
        )
        self.write({"signature_attachment_id": signature_attachment.id, "signed_device_id": device_id or False})
        pdf, _report_type = self.env["ir.actions.report"]._render_qweb_pdf(HANDOVER_RECORD_REPORT, self.ids)
        pdf_attachment = attachments.create(
            {
                "name": f"{self.code}.pdf",
                "raw": pdf,
                "mimetype": "application/pdf",
                "res_model": self._name,
                "res_id": self.id,
            }
        )
        partner = self.request_id.customer_id.partner_id
        self.env["mail.message"].raise_event(
            EVENT_HANDOVER_RECORD_SIGNED,
            self,
            f"handover_record:{self.id}:signed",
            self.with_context(lang=partner.lang).env._("Handover record %s is attached.", self.code),
            subject=self.code,
            partners=partner,
            attachments=pdf_attachment,
        )
        now = fields.Datetime.now()
        self.write(
            {
                "attachment_id": pdf_attachment.id,
                "signed_at": now,
                "sent_at": now if partner.email else False,
                "status": "signed",
            }
        )
