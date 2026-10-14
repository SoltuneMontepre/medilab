from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_CODE_MIXIN,
    MODEL_CONTACT_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_SUBCONTRACTOR,
)

RES_PARTNER = "res.partner"


# Thầu Phụ
class Subcontractor(models.Model):
    _name = MODEL_SUBCONTRACTOR
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_CODE_MIXIN, MODEL_CONTACT_MIXIN, MODEL_AUDIT_MIXIN]
    _inherits = {RES_PARTNER: "partner_id"}
    _description = "Subcontractor"
    _order = "code"
    _rec_names_search = ("name", "code")
    _permission_actions = ("create", "edit", "archive")
    # The subcontractor's permissions govern it, not Odoo's contact rights, which only administrators hold.
    _check_inherits_access = False
    _contact_fields = ("name", "vat", "street", "city", "country_id", "phone", "email")

    # Unique code of the subcontractor, such as TP.0001; filled from a sequence when left empty.
    code = fields.Char(required=True, copy=False, index="trigram")
    # The company contact of the subcontractor, which holds its name, address and people.
    partner_id = fields.Many2one(RES_PARTNER, required=True, ondelete="restrict")
    # The person the laboratory deals with by default; usually one of the company's people, but any person contact is allowed.
    contact_person_id = fields.Many2one(
        RES_PARTNER, ondelete="set null", index=True, domain=[("is_company", "=", False)]
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

    def _can_be_chosen(self):
        """True for a subcontractor in use whose accreditation has not expired; False for none."""
        subcontractor = self.sudo()
        expiry = subcontractor.accreditation_expiry
        return bool(subcontractor.active) and not (expiry and expiry < fields.Date.context_today(self))
