from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_SUBCONTRACTOR


# Liên Hệ
class ResPartner(models.Model):
    _inherit = "res.partner"

    # Subcontractors whose company contact this is.
    subcontractor_ids = fields.One2many(MODEL_SUBCONTRACTOR, "partner_id", string="Subcontractors")
    # True when Brevo reported a hard bounce or an invalid address. That address is not used again.
    email_bounced = fields.Boolean(copy=False)

    @api.depends("subcontractor_ids")
    def _compute_is_company(self):
        # Odoo counts a contact with a tax ID as a company; a subcontractor's contact is one too.
        result = super()._compute_is_company()
        for partner in self.filtered("subcontractor_ids"):
            partner.is_company = True
        return result
