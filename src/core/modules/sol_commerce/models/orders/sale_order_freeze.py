from odoo import models
from odoo.exceptions import UserError

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_commerce.constants.orders import (
    ADVANCE_FIELDS,
    FROZEN_ORDER_FIELDS,
    FROZEN_STATUSES,
    QUOTATION_FROZEN_STATUSES,
)


# Đơn Hàng: what the customer was quoted and what the confirmed order holds stays as it was.
class SaleOrderFreeze(models.Model):
    _inherit = MODEL_SALE_ORDER

    def write(self, vals):
        if FROZEN_ORDER_FIELDS & set(vals) and self._frozen_by_confirmation():
            raise UserError(self.env._("A confirmed order cannot be changed."))
        if ADVANCE_FIELDS & set(vals) and self._frozen_by_quotation():
            raise UserError(self.env._("The advance cannot change after the quotation is sent. Revise the quotation."))
        return super().write(vals)

    def _frozen_by_confirmation(self):
        """The orders that are confirmed or completed."""
        return self.sudo().filtered(lambda order: order.order_status in FROZEN_STATUSES)

    def _frozen_by_quotation(self):
        """The orders whose latest quotation is sent or accepted and that are not back in draft for a revision."""
        return self.sudo().filtered(
            lambda order: order.state != "draft" and order._latest_quotation().status in QUOTATION_FROZEN_STATUSES
        )

    def _check_content_freeze(self):
        """Refuse a change to the lines or samples of orders whose quotation was sent. Confirming needs an accepted
        quotation, so this also holds the lines and samples of every confirmed order."""
        if self.sudo()._frozen_by_quotation():
            raise UserError(self.env._("The quotation was sent; revise it before changing its lines or samples."))
