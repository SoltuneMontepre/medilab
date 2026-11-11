from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ACCREDITATION_CERTIFICATE,
    MODEL_AUDIT_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_ROLE,
    MODEL_ROLE_GRANT,
)
from odoo.addons.sol_laboratory.services.record_id import persisted_id

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_role_grant as RoleGrantBase
else:
    RoleGrantBase = object


# Vai Trò Có Hạn
class RoleGrant(models.Model, RoleGrantBase):
    _name = MODEL_ROLE_GRANT
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Role Until a Date"
    _order = "date_end, id"
    _permission_actions = ("read", "create", "edit", "delete")

    if not TYPE_CHECKING:
        # The person who holds the role until the date.
        person_id = fields.Many2one(MODEL_PERSON, string="Person", required=True, ondelete="cascade", index=True)
        # The role given to the person.
        role_id = fields.Many2one(MODEL_ROLE, string="Role", required=True, ondelete="cascade")
        # Last day the person holds the role; the role is removed once that day ends in the laboratory.
        date_end = fields.Date(string="Until", required=True)

    _role_unique = models.Constraint(
        "UNIQUE(person_id, role_id)", "The person is already given this role until a date."
    )

    @api.depends("person_id", "role_id")
    def _compute_display_name(self):
        for grant in self:
            grant.display_name = f"{grant.person_id.name or ''} - {grant.role_id.name or ''}"

    @api.model_create_multi
    def create(self, vals_list):
        grants = super().create(vals_list)
        grants._check_date_end()
        for grant in grants:
            person = grant.person_id
            if grant.role_id in person.sudo().role_ids:
                raise UserError(
                    self.env._(
                        "%(person)s already holds the role %(role)s.", person=person.name, role=grant.role_id.name
                    )
                )
            # Written as the user, so only those who may give roles to people give one until a date.
            person.role_ids = [Command.link(persisted_id(grant.role_id))]
        return grants

    def write(self, vals):
        if {"person_id", "role_id"} & set(vals):
            raise UserError(self.env._("Remove the role and give it again to change who holds it or which role it is."))
        result = super().write(vals)
        if "date_end" in vals:
            self._check_date_end()
        return result

    def unlink(self):
        held = [(grant.person_id, grant.role_id) for grant in self.sudo()]
        result = super().unlink()
        for person, role in held:
            if person.exists() and role in person.sudo().role_ids:
                person.with_env(self.env).role_ids = [Command.unlink(persisted_id(role))]
        return result

    def _check_date_end(self):
        today = self.env[MODEL_ACCREDITATION_CERTIFICATE]._laboratory_today()
        if any(not grant.date_end or grant.date_end < today for grant in self):
            raise UserError(self.env._("A role is given until today or a later day."))

    @api.model
    def _lapsed(self):
        """The roles whose last day has ended in the laboratory."""
        today = self.env[MODEL_ACCREDITATION_CERTIFICATE]._laboratory_today()
        return self.sudo().search([("date_end", "<", today)])
