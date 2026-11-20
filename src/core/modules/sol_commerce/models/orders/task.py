from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import STATUS_CLAIMED, STATUS_SUBMITTED
from odoo.addons.sol_commerce.constants.tasks import QUOTATION_ACTION, QUOTATION_TRIGGER
from odoo.addons.sol_laboratory.constants.models import MODEL_PERSON, MODEL_TASK

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_task as TaskBase
else:
    TaskBase = object


# Nhiệm Vụ: claiming the quotation task of an order claims the order.
class Task(models.Model, TaskBase):
    _inherit = MODEL_TASK

    def action_claim(self):
        quotations = self.filtered(lambda task: task.sudo()._opens_quotation())
        person = self.env[MODEL_PERSON]._current()
        for task in quotations.sudo():
            if task.assignee_id or task.status != "open":
                raise UserError(self.env._("%s is already claimed.", task.name))
            if not task._claimable_by(person):
                raise UserError(self.env._("%s waits in a queue you do not belong to.", task.name))
        if quotations:
            # Claiming the order gives its task to the same salesperson.
            self.env[MODEL_SALE_ORDER].browse(quotations.sudo().mapped("document_id")).action_claim()
        others = self - quotations
        if others:
            return super(Task, others).action_claim()
        return True

    def write(self, vals):
        result = super().write(vals)
        if "assignee_id" in vals:
            self._sync_quotation_order_assignee()
        return result

    def _sync_quotation_order_assignee(self):
        orders = self.env[MODEL_SALE_ORDER].sudo()
        for task in self.sudo().filtered(lambda item: item._opens_quotation() and item.assignee_id.user_id):
            order = orders.browse(task.document_id).exists()
            user = task.assignee_id.user_id
            if not order:
                continue
            if order.order_status == STATUS_SUBMITTED and not order.user_id:
                order._set_status(STATUS_CLAIMED, {"user_id": user.id, "claimed_at": fields.Datetime.now()})
            elif order.order_status == STATUS_CLAIMED and order.user_id != user:
                order.write({"user_id": user.id})

    def _opens_quotation(self):
        self.ensure_one()
        return (
            self.linked_by_system
            and self.document_model == MODEL_SALE_ORDER
            and self.action == QUOTATION_ACTION
            and self.type_id.trigger == QUOTATION_TRIGGER
        )
