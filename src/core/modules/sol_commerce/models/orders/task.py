from odoo import models
from odoo.exceptions import UserError

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.tasks import QUOTATION_ACTION, QUOTATION_TRIGGER
from odoo.addons.sol_laboratory.constants.models import MODEL_PERSON, MODEL_TASK


# Nhiệm Vụ: claiming the quotation task of an order claims the order.
class Task(models.Model):
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

    def _opens_quotation(self):
        self.ensure_one()
        return (
            self.linked_by_system
            and self.document_model == MODEL_SALE_ORDER
            and self.action == QUOTATION_ACTION
            and self.type_id.trigger == QUOTATION_TRIGGER
        )
