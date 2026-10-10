from odoo import api, fields, models

from odoo.addons.laboratory.constants.models import MODEL_ARCHIVE_MIXIN, MODEL_CODE_MIXIN, MODEL_SUBCONTRACTOR


# Thầu Phụ
class Subcontractor(models.Model):
    _name = MODEL_SUBCONTRACTOR
    _inherit = [MODEL_ARCHIVE_MIXIN, MODEL_CODE_MIXIN]
    _inherits = {"res.partner": "partner_id"}
    _description = "Subcontractor"
    _order = "code"
    _rec_names_search = ["name", "code"]

    # Unique code of the subcontractor, such as TP.0001; filled from a sequence when left empty.
    code = fields.Char(required=True, copy=False)
    # The company contact of the subcontractor, which holds its name, address and people.
    partner_id = fields.Many2one("res.partner", required=True, ondelete="restrict")
    # The person the laboratory deals with by default; usually one of the company's people, but any person contact is allowed.
    contact_person_id = fields.Many2one(
        "res.partner", ondelete="set null", index=True, domain=[("is_company", "=", False)]
    )
    # Number of the subcontractor's accreditation certificate, such as VILAS 123.
    accreditation_number = fields.Char()
    # Date the accreditation certificate expires; empty when it does not expire.
    accreditation_expiry = fields.Date()
    # Reference of the contract between the laboratory and the subcontractor.
    contract_reference = fields.Char()
    # Free notes about working with the subcontractor.
    note = fields.Text()
    # False when the laboratory no longer uses the subcontractor.
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a subcontractor must be unique.")
    _partner_unique = models.Constraint("UNIQUE(partner_id)", "This company is already a subcontractor.")

    @api.model_create_multi
    def create(self, vals_list):
        # A subcontractor created without an existing contact gets a new company contact.
        for vals in vals_list:
            if not vals.get("partner_id"):
                vals.setdefault("is_company", True)
        return super().create(vals_list)
