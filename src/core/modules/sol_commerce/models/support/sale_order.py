from psycopg2 import IntegrityError

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import mute_logger

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
        partner = self.env.user.partner_id
        rating = order.rating_ids.filtered(lambda item: not item.consumed and item.partner_id == partner)[:1]
        if not rating:
            rating = (
                self.env[MODEL_RATING]
                .sudo()
                .create(
                    {
                        "partner_id": partner.id,
                        "rated_partner_id": order.user_id.partner_id.id,
                        "res_model_id": self.env["ir.model"]._get_id(MODEL_SALE_ORDER),
                        "res_id": order.id,
                        "is_internal": False,
                    }
                )
            )
        try:
            with mute_logger("odoo.sql_db"), self.env.cr.savepoint():
                return order.rating_apply(value, rating=rating, feedback=(comment or "").strip() or False)
        except IntegrityError:
            # Another feedback on the order was saved meanwhile.
            self.env.invalidate_all()
            raise UserError(self.env._("This order already has feedback.")) from None

    def _get_allowed_message_params(self):
        # Feedback is given only through action_give_feedback, never as a value of a chatter message.
        return super()._get_allowed_message_params() - {"rating_value"}

    def message_post(self, **kwargs):
        if kwargs.get("rating_value") and not self.env.su:
            raise AccessError(self.env._("Feedback is given from the order's page in the portal."))
        return super().message_post(**kwargs)

    def _message_update_content(self, message, /, *, body, **kwargs):
        if message.sudo().rating_ids and not self.env.su:
            raise UserError(self.env._("Feedback cannot be changed once it is given."))
        return super()._message_update_content(message, body=body, **kwargs)
