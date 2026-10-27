from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_PERMISSION


# Quyền: a permission can let its holder create invoices from orders.
class Permission(models.Model):
    _inherit = MODEL_PERMISSION

    # The action the permission allows; invoice marks who may create invoices from an order, with no access of its own.
    action = fields.Selection(selection_add=[("invoice", "Invoice")], ondelete={"invoice": "cascade"})
