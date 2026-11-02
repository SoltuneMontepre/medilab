from typing import TYPE_CHECKING

from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER, MODEL_SUBCONTRACTOR

if TYPE_CHECKING:
    from medilab_model_types import Model_res_partner as ResPartnerBase
else:
    ResPartnerBase = object


# Liên Hệ
class ResPartner(models.Model, ResPartnerBase):
    _inherit = "res.partner"

    if not TYPE_CHECKING:
        # Subcontractors whose company contact this is.
        subcontractor_ids = fields.One2many(MODEL_SUBCONTRACTOR, "partner_id", string="Subcontractors")
        # Customers whose details this contact holds.
        customer_ids = fields.One2many(MODEL_CUSTOMER, "partner_id", string="Customers")
        # True when Brevo reported a hard bounce or an invalid address. That address is not used again.
        email_bounced = fields.Boolean(copy=False)

    @api.depends("subcontractor_ids", "customer_ids.citizen_id")
    def _compute_is_company(self):
        # Odoo counts a contact with a tax ID as a company; a subcontractor's contact is one too, and an individual
        # customer, identified by a citizen ID, is a person even with a tax code.
        result = super()._compute_is_company()
        for partner in self.filtered("subcontractor_ids"):
            partner.is_company = True
        for partner in self.filtered(lambda contact: bool(contact.sudo().customer_ids.citizen_id)):
            partner.is_company = False
        return result
