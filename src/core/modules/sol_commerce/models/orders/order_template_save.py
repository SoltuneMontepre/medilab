from typing import TYPE_CHECKING

from odoo import fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_ORDER_TEMPLATE, MODEL_ORDER_TEMPLATE_SAVE, MODEL_SALE_ORDER

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_order_template_save as OrderTemplateSaveBase
else:
    OrderTemplateSaveBase = object


# Lưu Đơn Hàng Mẫu
class OrderTemplateSave(models.TransientModel, OrderTemplateSaveBase):
    _name = MODEL_ORDER_TEMPLATE_SAVE
    _description = "Save an Order Template"

    if not TYPE_CHECKING:
        # The accessible source order whose selections will be saved.
        order_id = fields.Many2one(MODEL_SALE_ORDER, required=True, ondelete="cascade")
        # The name of the new template.
        name = fields.Char(required=True)

    def action_save(self):
        self.ensure_one()
        template = self.order_id._save_as_template(self.name)
        return {
            "type": "ir.actions.act_window",
            "res_model": MODEL_ORDER_TEMPLATE,
            "res_id": template.id,
            "view_mode": "form",
        }
