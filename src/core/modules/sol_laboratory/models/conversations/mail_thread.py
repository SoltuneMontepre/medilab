from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_laboratory.constants.models import MODEL_MAIL_THREAD

if TYPE_CHECKING:
    from medilab_model_types import Model_mail_thread as MailThreadBase
else:
    MailThreadBase = object


# Luồng Trao Đổi: a message that mentions people notifies them on each channel they keep on, and a message is pushed to
# the phones of the people it reaches.
class MailThread(models.AbstractModel, MailThreadBase):
    _inherit = MODEL_MAIL_THREAD

    def _notify_get_recipients(self, message, **kwargs):
        return message._mention_recipients(super()._notify_get_recipients(message, **kwargs))

    def _notify_thread(self, message, **kwargs):
        recipients = super()._notify_thread(message, **kwargs)
        message._notify_mentions_and_phones(self)
        return recipients
