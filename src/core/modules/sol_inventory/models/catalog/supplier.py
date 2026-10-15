from odoo import api, fields, models

from odoo.addons.sol_inventory.constants.models import MODEL_SUPPLIER
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_CODE_MIXIN,
    MODEL_CONTACT_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_RES_PARTNER,
)


# Nhà Cung Cấp
class Supplier(models.Model):
    _name = MODEL_SUPPLIER
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_CODE_MIXIN, MODEL_CONTACT_MIXIN, MODEL_AUDIT_MIXIN]
    _inherits = {MODEL_RES_PARTNER: "partner_id"}
    _description = "Supplier"
    _order = "code"
    _rec_names_search = ("name", "code")
    _permission_actions = ("create", "edit", "archive", "delete")
    # The supplier's permissions govern it, not Odoo's contact rights, which only administrators hold.
    _check_inherits_access = False
    _contact_fields = ("name", "vat", "street", "city", "country_id", "phone", "email")

    # Unique code of the supplier, such as NCC.0001; filled from a sequence when left empty.
    code = fields.Char(required=True, copy=False, index="trigram")
    # The company contact of the supplier, which holds its name, address and people.
    partner_id = fields.Many2one(MODEL_RES_PARTNER, required=True, ondelete="restrict")
    # The person the laboratory deals with by default at the supplier.
    contact_person_id = fields.Many2one(
        MODEL_RES_PARTNER, ondelete="set null", index=True, domain=[("is_company", "=", False)]
    )
    # Free notes about the supplier.
    note = fields.Text()
    # False when the laboratory no longer buys from the supplier.
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a supplier must be unique.")
    _partner_unique = models.Constraint("UNIQUE(partner_id)", "This company is already a supplier.")

    @api.model_create_multi
    def create(self, vals_list):
        suppliers = super().create(vals_list)
        # Odoo's Purchase app offers a contact as a vendor once its supplier rank is above zero.
        suppliers.partner_id.filtered(lambda contact: not contact.supplier_rank).sudo().supplier_rank = 1
        return suppliers
