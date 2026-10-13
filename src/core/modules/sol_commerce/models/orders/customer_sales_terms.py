from odoo import api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.sol_commerce.constants.models import MODEL_CUSTOMER_SALES_TERMS
from odoo.addons.sol_commerce.constants.xml_ids import ALL_ORDERS_GROUP
from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER, MODEL_PERMISSION_MIXIN


# Điều Khoản Bán Hàng
class CustomerSalesTerms(models.Model):
    _name = MODEL_CUSTOMER_SALES_TERMS
    _inherit = [MODEL_PERMISSION_MIXIN]
    _description = "Customer Sales Terms"
    _rec_name = "customer_id"
    _permission_actions = ("read", "create", "edit", "delete")

    # The customer.
    customer_id = fields.Many2one(MODEL_CUSTOMER, required=True, ondelete="cascade", index=True)
    # True when the customer may proceed without payment, so the request of their order is confirmed unpaid.
    allow_credit = fields.Boolean(default=False)

    _customer_unique = models.Constraint("UNIQUE(customer_id)", "A customer has only one set of sales terms.")

    @api.model_create_multi
    def create(self, vals_list):
        self._check_head_of_sales()
        return super().create(vals_list)

    def write(self, vals):
        self._check_head_of_sales()
        return super().write(vals)

    def _check_head_of_sales(self):
        if not (self.env.su or self.env.user.has_group(ALL_ORDERS_GROUP)):
            raise AccessError(self.env._("Only the Head of Sales can change the sales terms of a customer."))
