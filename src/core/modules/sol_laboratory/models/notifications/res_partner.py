import hashlib
import json
import secrets
from typing import TYPE_CHECKING
from urllib.parse import urljoin

from odoo import fields, models
from odoo.fields import Command

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_CONFIG_PARAMETER,
    MODEL_MAIL_MAIL,
    MODEL_MAIL_MESSAGE,
    MODEL_MAIL_NOTIFICATION,
    MODEL_RES_PARTNER,
    MODEL_SCHEDULED_JOB,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_res_partner as ResPartnerBase
else:
    ResPartnerBase = object


# Liên Hệ
class ResPartner(models.Model, ResPartnerBase):
    _inherit = MODEL_RES_PARTNER

    if not TYPE_CHECKING:
        # SHA-256 digest of the one-use token sent to a corrected address.
        email_confirmation_token = fields.Char(copy=False, groups="base.group_system")

    def write(self, vals):
        corrected = self.filtered(
            lambda partner: partner.email_bounced
            and vals.get("email")
            and (partner.email or "").strip().lower() != vals["email"].strip().lower()
        )
        result = super().write(vals)
        for partner in corrected:
            partner._send_email_confirmation()
        return result

    def _send_email_confirmation(self):
        self.ensure_one()
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        self.sudo().write({"email_confirmation_token": digest})
        base_url = self.env[MODEL_IR_CONFIG_PARAMETER].sudo().get_param("web.base.url")
        confirmation_url = urljoin(f"{base_url.rstrip('/')}/", f"medilab/email/confirm/{token}")
        body = self.env._(
            'Confirm your corrected email address by opening <a href="%s">this link</a>.', confirmation_url
        )
        message = self.env[MODEL_MAIL_MESSAGE].sudo().create(
            {
                "model": MODEL_RES_PARTNER,
                "res_id": self.id,
                "subject": self.env._("Confirm your email address"),
                "body": body,
                "message_type": "email",
            }
        )
        mail = self.env[MODEL_MAIL_MAIL].sudo().create(
            {
                "subject": message.subject,
                "body_html": message.body,
                "email_from": self.env.company.email or self.env.user.email or "notifications@localhost",
                "email_to": self.email,
                "recipient_ids": [Command.link(self.id)],
                "email_confirmation": True,
                "mail_message_id": message.id,
                "auto_delete": False,
                "state": "outgoing",
            }
        )
        notification = self.env[MODEL_MAIL_NOTIFICATION].sudo().create(
            {
                "mail_message_id": message.id,
                "res_partner_id": self.id,
                "notification_type": "email",
                "notification_status": "ready",
                "mail_mail_id": mail.id,
            }
        )
        mail.headers = json.dumps({"X-Mailin-custom": f"notification:{notification.id}"})
        self.env[MODEL_SCHEDULED_JOB].queue("notifications.email", f"email-confirmation:{mail.id}", document=mail)

    def _confirm_email_address(self, token):
        digest = hashlib.sha256((token or "").encode()).hexdigest()
        partner = self.sudo().search(
            [("email_confirmation_token", "=", digest), ("email_bounced", "=", True)], limit=1
        )
        if not partner:
            return self.browse()
        partner.write({"email_bounced": False, "email_confirmation_token": False})
        self.env["medilab.audit.entry"]._log_event(
            "integration", self.env._("Customer email address confirmed"), partner
        )
        return partner
