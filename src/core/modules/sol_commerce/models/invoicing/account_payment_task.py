from typing import TYPE_CHECKING

from odoo import api, models
from odoo.tools.misc import formatLang

from odoo.addons.sol_commerce.constants.models import MODEL_ACCOUNT_PAYMENT
from odoo.addons.sol_commerce.constants.tasks import PAYMENT_REVIEW_ACTION, PAYMENT_REVIEW_TRIGGER
from odoo.addons.sol_commerce.models.invoicing.account_move import ADMINISTRATOR_GROUP, BILLING_GROUP
from odoo.addons.sol_laboratory.constants.models import MODEL_TASK, MODEL_TASK_TYPE
from odoo.addons.sol_laboratory.services.staff_language import staff_env

if TYPE_CHECKING:
    from medilab_model_types import Model_account_payment as AccountPaymentBase
else:
    AccountPaymentBase = object

# Methods the accountant confirms by checking the bank account or the cash box.
REVIEWED_METHODS = ("bank_transfer", "cash")


# Phiếu thu: the task that asks the accountant to confirm a cash or transfer payment someone else recorded.
class AccountPaymentTask(models.Model, AccountPaymentBase):
    _inherit = MODEL_ACCOUNT_PAYMENT

    @api.model_create_multi
    def create(self, vals_list):
        payments = super().create(vals_list)
        payments._create_review_task()
        return payments

    def action_post(self):
        result = super().action_post()
        self.env[MODEL_TASK]._close_for_document(self, PAYMENT_REVIEW_ACTION)
        return result

    def action_cancel(self):
        result = super().action_cancel()
        self.env[MODEL_TASK]._cancel_for_document(self, PAYMENT_REVIEW_ACTION)
        return result

    def unlink(self):
        self.env[MODEL_TASK]._cancel_for_document(self, PAYMENT_REVIEW_ACTION)
        return super().unlink()

    def _create_review_task(self):
        """Put each pending cash or transfer payment in the accountants' queue when the person who recorded it, a
        salesperson or the customer on the portal, cannot confirm it."""
        user = self.env.user
        if user.has_group(BILLING_GROUP) or user.has_group(ADMINISTRATOR_GROUP):
            return
        tasks = self.env[MODEL_TASK].sudo()
        for payment in self.sudo().filtered(lambda item: item.state == "draft" and item.method in REVIEWED_METHODS):
            if not tasks._system_tasks_of(payment, PAYMENT_REVIEW_ACTION):
                env = staff_env(self.env)
                task_type = env[MODEL_TASK_TYPE].sudo().search([("trigger", "=", PAYMENT_REVIEW_TRIGGER)], limit=1)
                # A draft payment has no number yet; the task names what the accountant looks for in the bank account.
                amount = formatLang(env, payment.amount, currency_obj=payment.currency_id)
                reference = payment.memo or payment.partner_id.name
                tasks._create_for_event(
                    PAYMENT_REVIEW_TRIGGER, payment, name=f"{task_type.name}: {reference}, {amount}"
                )
