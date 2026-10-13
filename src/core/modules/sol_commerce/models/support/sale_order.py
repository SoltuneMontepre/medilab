from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_commerce.constants.models import MODEL_RATING, MODEL_SALE_ORDER, MODEL_SUPPORT_REQUEST
from odoo.addons.sol_commerce.constants.orders import STATUS_COMPLETED
from odoo.addons.sol_commerce.constants.support import FEEDBACK_MAX, FEEDBACK_MIN


# Đơn Hàng: the support requests about the order and the customer's feedback on it.
class SaleOrder(models.Model):
    _inherit = MODEL_SALE_ORDER

    # Support requests about the order.
    support_request_ids = fields.One2many(MODEL_SUPPORT_REQUEST, "order_id", string="Support Requests")
    # The rating the customer gave, from 1 to 5; 0 while the order has no feedback.
    feedback_rating = fields.Integer(compute="_compute_feedback", compute_sudo=True)
    # The customer's comment with the rating.
    feedback_comment = fields.Text(compute="_compute_feedback", compute_sudo=True)

    @api.depends("rating_ids.rating", "rating_ids.feedback", "rating_ids.consumed")
    def _compute_feedback(self):
        for order in self:
            feedback = order._feedback()
            order.feedback_rating = int(feedback.rating) if feedback else 0
            order.feedback_comment = feedback.feedback if feedback else False

    def _feedback(self):
        self.ensure_one()
        return self.sudo().rating_ids.filtered("consumed")[:1]

    def can_give_feedback(self):
        self.ensure_one()
        return self.order_status == STATUS_COMPLETED and not self._feedback()

    def action_give_feedback(self, rate, comment=None):
        """Rate the completed order once, from 1 to 5 with an optional comment."""
        self.ensure_one()
        self._check_customer_owner()
        if self.order_status != STATUS_COMPLETED:
            raise UserError(self.env._("Feedback can be given once the order is completed."))
        if self._feedback():
            raise UserError(self.env._("This order already has feedback."))
        try:
            value = int(rate)
        except (TypeError, ValueError):
            value = 0
        if not FEEDBACK_MIN <= value <= FEEDBACK_MAX:
            raise UserError(self.env._("Give a rating from 1 to 5."))
        order = self.sudo()
        rating = order.rating_ids.filtered(lambda item: not item.consumed)[:1]
        if not rating:
            rating = (
                self.env[MODEL_RATING]
                .sudo()
                .create(
                    {
                        "partner_id": self.env.user.partner_id.id,
                        "rated_partner_id": order.user_id.partner_id.id,
                        "res_model_id": self.env["ir.model"]._get_id(MODEL_SALE_ORDER),
                        "res_id": order.id,
                        "is_internal": False,
                    }
                )
            )
        return order.rating_apply(value, rating=rating, feedback=(comment or "").strip() or False)
