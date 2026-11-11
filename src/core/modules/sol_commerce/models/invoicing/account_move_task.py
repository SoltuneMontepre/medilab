from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_MOVE
from odoo.addons.sol_commerce.constants.tasks import AUTO_POST_CONTEXT, POSTING_ACTION, POSTING_TRIGGER
from odoo.addons.sol_commerce.models.invoicing.account_move import ADMINISTRATOR_GROUP, BILLING_GROUP
from odoo.addons.sol_laboratory.constants.models import MODEL_TASK

if TYPE_CHECKING:
    from medilab_model_types import Model_account_move as AccountMoveBase
else:
    AccountMoveBase = object

POSTED_KINDS = ("advance", "final")


# Hóa đơn: the posting task of an invoice drafted by someone who cannot post it.
class AccountMove(models.Model, AccountMoveBase):
    _inherit = MODEL_ACCOUNT_MOVE

    def write(self, vals):
        result = super().write(vals)
        if vals.get("invoice_kind") in POSTED_KINDS and not self.env.context.get(AUTO_POST_CONTEXT):
            self._create_posting_task()
        return result

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        self.env[MODEL_TASK]._close_for_document(posted, POSTING_ACTION)
        return posted

    def button_cancel(self):
        result = super().button_cancel()
        self.env[MODEL_TASK]._cancel_for_document(self, POSTING_ACTION)
        return result

    def unlink(self):
        self.env[MODEL_TASK]._cancel_for_document(self, POSTING_ACTION)
        return super().unlink()

    def _create_posting_task(self):
        """Put each draft invoice in the accountants' queue when the person who drafted it cannot post it. Sales
        drafts invoices with full rights, so the check reads the person, not the environment."""
        user = self.env.user
        if user.has_group(BILLING_GROUP) or user.has_group(ADMINISTRATOR_GROUP):
            return
        tasks = self.env[MODEL_TASK]
        for move in self.filtered(lambda item: item.move_type == "out_invoice" and item.state == "draft"):
            if not tasks._system_tasks_of(move, POSTING_ACTION):
                tasks._create_for_event(POSTING_TRIGGER, move)
