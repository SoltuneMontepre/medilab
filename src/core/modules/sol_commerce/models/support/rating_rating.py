from odoo import models

from odoo.addons.sol_commerce.constants.models import MODEL_RATING


# Phản Hồi: a completed order has at most one feedback.
class RatingRating(models.Model):
    _inherit = MODEL_RATING

    _order_unique = models.UniqueIndex(
        "(res_model, res_id) WHERE res_model = 'sale.order'", "An order has at most one feedback."
    )
