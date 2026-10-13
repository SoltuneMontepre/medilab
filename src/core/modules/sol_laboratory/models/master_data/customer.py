from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_CODE_MIXIN,
    MODEL_CUSTOMER,
    MODEL_PERMISSION_MIXIN,
)


# Khách Hàng
class Customer(models.Model):
    _name = MODEL_CUSTOMER
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_CODE_MIXIN]
    _inherits = {"res.partner": "partner_id"}
    _description = "Customer"
    _order = "code"
    _rec_names_search = ("name", "code")

    # Unique code of the customer, such as KH.0001; filled from a sequence when left empty.
    code = fields.Char(required=True, copy=False)
    # The contact holding the customer's details: name, address, email, phone, and for a company its people.
    partner_id = fields.Many2one("res.partner", required=True, ondelete="restrict")
    # False when the customer is archived.
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a customer must be unique.")
    _partner_unique = models.Constraint("UNIQUE(partner_id)", "This contact is already a customer.")
