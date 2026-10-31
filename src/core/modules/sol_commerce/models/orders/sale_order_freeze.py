from typing import TYPE_CHECKING

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import ADVANCE_FIELDS, QUOTATION_FROZEN_STATUSES
from odoo.addons.sol_laboratory.constants.approvals import APPROVAL_SYSTEM_CONTEXT

if TYPE_CHECKING:
    from medilab_model_types import Model_sale_order as SaleOrderFreezeBase
else:
    SaleOrderFreezeBase = object


# Đơn Hàng: what the customer was quoted and what sales signed stays as it was.
class SaleOrderFreeze(models.Model, SaleOrderFreezeBase):
    _inherit = MODEL_SALE_ORDER

    def write(self, vals):
        if ADVANCE_FIELDS & set(vals) and self._frozen_by_quotation():
            raise UserError(self.env._("The advance cannot change after the quotation is sent. Revise the quotation."))
        return super().write(vals)

    def _frozen_by_quotation(self):
        """The orders whose latest quotation is sent or accepted and that are not back in draft for a revision."""
        return self.sudo().filtered(
            lambda order: order.state != "draft" and order._latest_quotation().status in QUOTATION_FROZEN_STATUSES
        )

    def _check_content_freeze(self):
        """Refuse a change to the lines or samples of orders with a standing signature or a quotation that was sent."""
        orders = self.sudo()
        if not self.env.context.get(APPROVAL_SYSTEM_CONTEXT) and orders._approval_has_standing():
            raise UserError(self.env._("The order has signatures; withdraw them before changing its lines or samples."))
        if orders._frozen_by_quotation():
            raise UserError(self.env._("The quotation was sent; revise it before changing its lines or samples."))
