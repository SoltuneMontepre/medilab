from odoo import api, fields, models

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_CODE_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_SUBCONTRACTOR,
)

CONTACT_FIELDS = ("name", "vat", "street", "city", "country_id", "phone", "email")
RES_PARTNER = "res.partner"


# Thầu Phụ
class Subcontractor(models.Model):
    _name = MODEL_SUBCONTRACTOR
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN, MODEL_CODE_MIXIN]
    _inherits = {RES_PARTNER: "partner_id"}
    _description = "Subcontractor"
    _order = "code"
    _rec_names_search = ("name", "code")
    _permission_actions = ("create", "edit", "archive")
    # The subcontractor's permissions govern it, not Odoo's contact rights, which only administrators hold.
    _check_inherits_access = False

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

    def _prepare_create_values(self, vals_list):
        # Odoo always adds the contact's properties, which would write the contact as the user.
        prepared = super()._prepare_create_values(vals_list)
        for vals, given in zip(prepared, vals_list, strict=True):
            if "properties" not in given:
                vals.pop("properties", None)
        return prepared

    @api.model_create_multi
    def create(self, vals_list):
        # The subcontractor's permissions cover its company contact, which Odoo lets only contact managers create.
        self.check_access("create")
        for vals in vals_list:
            if vals.get("partner_id"):
                self.env[RES_PARTNER].browse(vals["partner_id"]).check_access("write")
            else:
                contact = {field_name: vals.pop(field_name) for field_name in CONTACT_FIELDS if field_name in vals}
                vals["partner_id"] = self.env[RES_PARTNER].sudo().create(contact).id
        return super().create(vals_list)

    def write(self, vals):
        if "partner_id" in vals:
            self.env[RES_PARTNER].browse(vals["partner_id"]).check_access("write")
        contact = {field_name: vals[field_name] for field_name in CONTACT_FIELDS if field_name in vals}
        vals = {field_name: value for field_name, value in vals.items() if field_name not in contact}
        if contact:
            self._check_permission("edit")
        result = super().write(vals) if vals else True
        if contact:
            self.sudo().partner_id.write(contact)
        return result
