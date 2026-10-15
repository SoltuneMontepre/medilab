from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.departments import DEPARTMENT_DOMAIN
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_MIXIN,
    MODEL_AUDIT_MIXIN,
    MODEL_DEPARTMENT,
    MODEL_EMPLOYEE_VERSION,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
)


# Phòng Ban
class HrDepartment(models.Model):
    # _name is required to add mixins to an Odoo model.
    _name = MODEL_DEPARTMENT
    _inherit = [MODEL_AUDIT_MIXIN, MODEL_DEPARTMENT, MODEL_PERMISSION_MIXIN, MODEL_ARCHIVE_MIXIN]

    # The department a team belongs to; empty for a department. A team cannot have teams of its own.
    parent_id = fields.Many2one(domain=DEPARTMENT_DOMAIN)
    # People of the team; empty for a department, whose people are its employees.
    team_person_ids = fields.One2many(MODEL_PERSON, "team_id", string="Team Members")

    @api.constrains("parent_id")
    def _check_team_level(self):
        for department in self.filtered("parent_id"):
            if department.parent_id.parent_id:
                raise ValidationError(
                    self.env._(
                        "%(team)s cannot belong to %(parent)s, which is a team itself.",
                        team=department.name,
                        parent=department.parent_id.name,
                    )
                )
            if department.with_context(active_test=False).child_ids or department._named_as_department():
                raise ValidationError(
                    self.env._(
                        "%s has teams of its own or records that name it as their department, so it cannot "
                        "become a team.",
                        department.name,
                    )
                )
        for team in self:
            if team.sudo().with_context(active_test=False).team_person_ids._outside_their_department():
                raise ValidationError(
                    self.env._(
                        "The people of %s belong to its department; take them out of the team before moving it.",
                        team.name,
                    )
                )

    def _named_as_department(self):
        self.ensure_one()
        return any(
            self._referrer_names(field, archiving=False)
            for field in self._referring_fields()
            if field.name == "department_id"
        )

    def _search_has_read_access(self, operator, value):
        # Odoo's Departments menu lists only the departments they manage to people who cannot read employees.
        if operator == "in" and self._has_permission("read"):
            return Domain.TRUE
        return super()._search_has_read_access(operator, value)

    def _referring_fields(self):
        # People name their department through their employee's version; the person stands for it. Odoo's root
        # department of a team is computed from its parent, which already names the team.
        referring = [
            field
            for field in super()._referring_fields()
            if field.model_name != MODEL_EMPLOYEE_VERSION and not field.compute
        ]
        return [*referring, self.env[MODEL_PERSON]._fields["department_id"]]
