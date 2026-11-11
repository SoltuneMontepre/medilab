from typing import TYPE_CHECKING

from odoo import models

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import STATUS_CANCELLED, STATUS_SUBMITTED
from odoo.addons.sol_commerce.constants.tasks import QUOTATION_ACTION, QUOTATION_TRIGGER
from odoo.addons.sol_laboratory.constants.models import MODEL_PERSON, MODEL_TASK

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderBase
else:
    SaleOrderBase = object


# Đơn Hàng: the quotation task that follows an order from the sales queue to its first quotation.
class SaleOrder(models.Model, SaleOrderBase):
    _inherit = MODEL_SALE_ORDER

    def write(self, vals):
        result = super().write(vals)
        if "user_id" in vals:
            self._give_quotation_task()
        return result

    def _set_status(self, status, extra=None):
        result = super()._set_status(status, extra)
        if status == STATUS_SUBMITTED:
            self._create_quotation_task()
        elif status == STATUS_CANCELLED:
            self.env[MODEL_TASK]._cancel_for_document(self, QUOTATION_ACTION)
        return result

    def _send_quotation(self):
        quotation = super()._send_quotation()
        self.env[MODEL_TASK]._close_for_document(self, QUOTATION_ACTION)
        return quotation

    def _create_quotation_task(self):
        """Put each submitted order in the sales queue as a task, once."""
        tasks = self.env[MODEL_TASK]
        for order in self:
            if not tasks._system_tasks_of(order, QUOTATION_ACTION):
                tasks._create_for_event(QUOTATION_TRIGGER, order)

    def _give_quotation_task(self):
        """Give the open quotation task of each order to the order's salesperson."""
        tasks = self.env[MODEL_TASK]
        people = self.env[MODEL_PERSON].sudo()
        for order in self.filtered("user_id"):
            person = people.search([("user_id", "=", order.user_id.id)], limit=1)
            if not person:
                continue
            for task in tasks._system_tasks_of(order, QUOTATION_ACTION).filtered(lambda t: t.assignee_id != person):
                vals = {"assignee_id": person.id}
                if task.assignee_id:
                    vals["reassign_reason"] = self.env._("The order's salesperson changed.")
                else:
                    vals.update({"assigned_by_id": person.id, "status": "assigned"})
                task.write(vals)
