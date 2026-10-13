from odoo import api, fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_RATING, MODEL_SALE_ORDER


# Phản Hồi: the feedback of an order follows the order's access, and an order has at most one.
class RatingRating(models.Model):
    _inherit = MODEL_RATING

    # The order the rating is about, for ratings of orders; access rules on order feedback follow it.
    order_id = fields.Many2one(
        MODEL_SALE_ORDER, compute="_compute_order_id", store=True, index="btree_not_null", ondelete="cascade"
    )

    _order_feedback_unique = models.UniqueIndex(
        "(res_id) WHERE res_model = 'sale.order' AND consumed", "An order has at most one feedback."
    )

    @api.depends("res_model", "res_id")
    def _compute_order_id(self):
        for rating in self:
            rating.order_id = rating.res_id if rating.res_model == MODEL_SALE_ORDER else False
