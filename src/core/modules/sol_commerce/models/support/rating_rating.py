from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_commerce.constants.models import MODEL_RATING, MODEL_SALE_ORDER
from odoo.addons.sol_laboratory.constants.models import MODEL_AUDIT_MIXIN

if TYPE_CHECKING:
    from medilab_model_types import Model_rating_rating as RatingRatingBase
else:
    RatingRatingBase = object


# Phản Hồi: the feedback of an order follows the order's access, and an order has at most one.
class RatingRating(models.Model, RatingRatingBase):
    _name = MODEL_RATING
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_RATING]

    if not TYPE_CHECKING:
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

    def _audit_scope(self):
        # Only the feedback on orders is a MediLab document; the ratings of other Odoo apps stay out of the trail.
        return self.filtered(lambda rating: rating.sudo().res_model == MODEL_SALE_ORDER)

    def _audit_parents(self):
        # The feedback is part of its order, so the order's history keeps it.
        return {rating.id: (MODEL_SALE_ORDER, rating.order_id.id) for rating in self.sudo() if rating.order_id}
