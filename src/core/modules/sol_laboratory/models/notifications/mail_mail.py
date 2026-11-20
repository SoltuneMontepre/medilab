from email.utils import getaddresses
from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY, MODEL_MAIL_MAIL, MODEL_RES_PARTNER

if TYPE_CHECKING:
    from medilab_model_types import Model_mail_mail as MailMailBase
else:
    MailMailBase = object


# Email Gửi Đi
class MailMail(models.Model, MailMailBase):
    _inherit = MODEL_MAIL_MAIL

    if not TYPE_CHECKING:
        # True only for the link that confirms a corrected bounced address.
        email_confirmation = fields.Boolean(default=False, copy=False)

    def send(self, auto_commit=False, raise_exception=False, post_send_callback=None):
        blocked = self.filtered(lambda mail: not mail.email_confirmation and mail._has_bounced_recipient())
        if blocked:
            entries = self.env[MODEL_AUDIT_ENTRY]
            for mail in blocked:
                entries._log_event(
                    "error",
                    self.env._("Email not sent because the recipient's address is bounced."),
                    mail.mail_message_id._audit_document(),
                )
            blocked.sudo().write(
                {
                    "state": "cancel",
                    "failure_type": "mail_bounce",
                    "failure_reason": self.env._("The recipient's email address must be confirmed before sending."),
                }
            )
        allowed = self - blocked
        if not allowed:
            return None
        return super(MailMail, allowed).send(
            auto_commit=auto_commit,
            raise_exception=raise_exception,
            post_send_callback=post_send_callback,
        )

    def _has_bounced_recipient(self):
        self.ensure_one()
        if any(self.recipient_ids.mapped("email_bounced")):
            return True
        addresses = {email.strip().lower() for _name, email in getaddresses([self.email_to or ""]) if email}
        return bool(
            addresses
            and self.env[MODEL_RES_PARTNER].sudo().search_count(
                [("email_bounced", "=", True), ("email", "in", list(addresses))]
            )
        )

    def _postprocess_sent_message(self, success_pids, success_emails, failure_reason=False, failure_type=None):
        # Every email leaves through the mail server, Brevo in production. It is recorded before Odoo deletes a sent
        # email.
        entries = self.env[MODEL_AUDIT_ENTRY]
        for mail in self:
            document = mail.mail_message_id._audit_document()
            if failure_type and not success_pids and not success_emails:
                entries._log_event("error", self.env._("Email not sent: %s", failure_reason or failure_type), document)
            else:
                entries._log_event("integration", self.env._("Email sent: %s", mail.subject or ""), document)
        return super()._postprocess_sent_message(
            success_pids, success_emails, failure_reason=failure_reason, failure_type=failure_type
        )
