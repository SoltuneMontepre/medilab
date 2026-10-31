from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_CODE_MIXIN,
    MODEL_CONTACT_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_SUBCONTRACTOR,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_subcontractor as SubcontractorBase
else:
    SubcontractorBase = object

RES_PARTNER = "res.partner"


# Thầu Phụ
class Subcontractor(models.Model, SubcontractorBase):
    _name = MODEL_SUBCONTRACTOR
    _inherit = [
        MODEL_PERMISSION_MIXIN,
        MODEL_LOCK_MIXIN,
        MODEL_ARCHIVE_MIXIN,
        MODEL_CODE_MIXIN,
        MODEL_CONTACT_MIXIN,
        MODEL_AUDIT_MIXIN,
    ]
    _inherits = {RES_PARTNER: "partner_id"}
    _description = "Subcontractor"
    _order = "code"
    _rec_names_search = ("name", "code")
    _permission_actions = ("create", "edit", "archive")
    # The subcontractor's permissions govern it, not Odoo's contact rights, which only administrators hold.
    _check_inherits_access = False
    _contact_fields = ("name", "vat", "street", "city", "country_id", "phone", "email")

    if not TYPE_CHECKING:
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
        # True while the expiry date is in the past; such a subcontractor cannot be chosen on a way of testing.
        accreditation_expired = fields.Boolean(
            compute="_compute_accreditation_expired", search="_search_accreditation_expired"
        )
        # Reference of the contract between the laboratory and the subcontractor.
        contract_reference = fields.Char()
        # Free notes about working with the subcontractor.
        note = fields.Text()
        # False when the laboratory no longer uses the subcontractor.
        active = fields.Boolean(default=True)

    _code_unique = models.Constraint("UNIQUE(code)", "The code of a subcontractor must be unique.")
    _partner_unique = models.Constraint("UNIQUE(partner_id)", "This company is already a subcontractor.")

    @api.depends("accreditation_expiry")
    def _compute_accreditation_expired(self):
        today = fields.Date.context_today(self)
        for subcontractor in self:
            expiry = subcontractor.accreditation_expiry
            subcontractor.accreditation_expired = bool(expiry and expiry < today)

    def _search_accreditation_expired(self, operator, value):
        # Odoo rewrites a boolean comparison as "in" or "not in" {True} before calling a search method.
        if operator not in ("in", "not in") or True not in value:
            return NotImplemented
        expired = Domain("accreditation_expiry", "<", fields.Date.context_today(self))
        return expired if operator == "in" else ~expired

    def _can_be_chosen(self):
        """True for a subcontractor in use whose accreditation has not expired; False for none."""
        subcontractor = self.sudo()
        return bool(subcontractor.active) and not subcontractor.accreditation_expired
