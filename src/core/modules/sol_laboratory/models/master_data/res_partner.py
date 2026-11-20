import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_CUSTOMER,
    MODEL_MAIL_MAIL,
    MODEL_SCHEDULED_JOB,
    MODEL_SUBCONTRACTOR,
)
from odoo.addons.sol_laboratory.constants.routes import CUSTOMER_EMAIL_CONFIRMATION_PATH

if TYPE_CHECKING:
    from medilab_model_types import Model_res_partner as ResPartnerBase
else:
    ResPartnerBase = object


# Liên Hệ
class ResPartner(models.Model, ResPartnerBase):
    _inherit = "res.partner"

    if not TYPE_CHECKING:
        # Subcontractors whose company contact this is.
        subcontractor_ids = fields.One2many(MODEL_SUBCONTRACTOR, "partner_id", string="Subcontractors")
        # Customers whose details this contact holds.
        customer_ids = fields.One2many(MODEL_CUSTOMER, "partner_id", string="Customers")
        # True when Brevo reported a hard bounce or an invalid address. That address is not used again.
        email_bounced = fields.Boolean(copy=False)
        # Hash of the single-use token sent to a corrected contact email address.
        email_confirmation_token_hash = fields.Char(copy=False, groups="base.group_system")
        # When the confirmation token for the corrected contact email expires.
        email_confirmation_expires_at = fields.Datetime(copy=False, groups="base.group_system")

    def write(self, values):
        if values.get("email_bounced") is False:
            bounced = self.filtered("email_bounced")
            corrected_email = (values.get("email") or "").strip().lower()
            if bounced and any((partner.email or "").strip().lower() == corrected_email for partner in bounced):
                raise AccessError(self.env._("A bounced email address can only be cleared by its confirmation link."))
        if "email" not in values:
            return super().write(values)
        for partner in self:
            new_email = (values.get("email") or "").strip()
            old_email = (partner.email or "").strip()
            if not partner.email_bounced or new_email.lower() == old_email.lower():
                super(ResPartner, partner).write(values)
                continue
            corrected_values = dict(values, email_bounced=True)
            super(ResPartner, partner).write(corrected_values)
            if not partner.email:
                super(ResPartner, partner.sudo()).write(
                    {"email_confirmation_token_hash": False, "email_confirmation_expires_at": False}
                )
                continue
            token = secrets.token_urlsafe(32)
            expiry = fields.Datetime.now() + timedelta(hours=24)
            super(ResPartner, partner.sudo()).write(
                {
                    "email_confirmation_token_hash": hashlib.sha256(token.encode()).hexdigest(),
                    "email_confirmation_expires_at": expiry,
                }
            )
            partner.sudo()._send_corrected_email_confirmation(token)
        return True

    def _send_corrected_email_confirmation(self, token):
        self.ensure_one()
        url = f"{self.get_base_url()}{CUSTOMER_EMAIL_CONFIRMATION_PATH}/{self.id}?{urlencode({'token': token})}"
        body = Markup('<p>{}</p><p><a href="{}">{}</a></p>').format(
            escape(self.env._("Confirm that this is your email address.")),
            escape(url),
            escape(self.env._("Confirm email address")),
        )
        mail = (
            self.env[MODEL_MAIL_MAIL]
            .sudo()
            .create(
                {
                    "subject": self.env._("Confirm your email address"),
                    "body_html": str(body),
                    "email_from": self.env.company.email or self.env.user.email or "notifications@localhost",
                    "email_to": self.email,
                    "auto_delete": False,
                    "state": "outgoing",
                }
            )
        )
        stamp = fields.Datetime.to_string(self.email_confirmation_expires_at)
        self.env[MODEL_SCHEDULED_JOB].queue(
            "notifications.email", f"email-confirmation:{self.id}:{stamp}", document=mail
        )

    def _confirm_corrected_email(self, token):
        self.ensure_one()
        if not token or not self.email or not self.email_bounced or not self.email_confirmation_token_hash:
            return False
        if not self.email_confirmation_expires_at or self.email_confirmation_expires_at <= fields.Datetime.now():
            return False
        digest = hashlib.sha256(token.encode()).hexdigest()
        if not hmac.compare_digest(digest, self.email_confirmation_token_hash):
            return False
        super().write(
            {
                "email_bounced": False,
                "email_confirmation_token_hash": False,
                "email_confirmation_expires_at": False,
            }
        )
        return True

    @api.depends("subcontractor_ids", "customer_ids.citizen_id")
    def _compute_is_company(self):
        # Odoo counts a contact with a tax ID as a company; a subcontractor's contact is one too, and an individual
        # customer, identified by a citizen ID, is a person even with a tax code.
        result = super()._compute_is_company()
        for partner in self.filtered("subcontractor_ids"):
            partner.is_company = True
        for partner in self.filtered(lambda contact: bool(contact.sudo().customer_ids.citizen_id)):
            partner.is_company = False
        return result
