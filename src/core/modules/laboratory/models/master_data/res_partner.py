from odoo import api, fields, models

from odoo.addons.laboratory.constants.models import MODEL_SUBCONTRACTOR


# Liên Hệ
class ResPartner(models.Model):
    _inherit = "res.partner"

    # Subcontractors whose company contact this is.
    subcontractor_ids = fields.One2many(MODEL_SUBCONTRACTOR, "partner_id", string="Subcontractors")

    @api.depends("subcontractor_ids")
    def _compute_is_company(self):
        # Odoo counts a contact with a tax ID as a company; a subcontractor's contact is one too.
        result = super()._compute_is_company()
        for partner in self.filtered("subcontractor_ids"):
            partner.is_company = True
        return result
