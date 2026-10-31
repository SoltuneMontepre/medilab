from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_ENTRY, MODEL_MAIL_MAIL

if TYPE_CHECKING:
    from medilab_model_types import Model_mail_mail as MailMailBase
else:
    MailMailBase = object


# Email Gửi Đi
class MailMail(models.Model, MailMailBase):
    _inherit = MODEL_MAIL_MAIL

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
