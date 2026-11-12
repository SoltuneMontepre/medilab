from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.tools import format_list

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_MIXIN,
    MODEL_LOCK_MIXIN,
    MODEL_PARAMETER_AUTHORIZATION,
    MODEL_PERMISSION_MIXIN,
    MODEL_PERSON,
    MODEL_TEST_PARAMETER,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_parameter_authorization as ParameterAuthorizationBase
else:
    ParameterAuthorizationBase = object


# Quyền Thử Chỉ Tiêu
class ParameterAuthorization(models.Model, ParameterAuthorizationBase):
    _name = MODEL_PARAMETER_AUTHORIZATION
    _inherit = [MODEL_PERMISSION_MIXIN, MODEL_LOCK_MIXIN, MODEL_AUDIT_MIXIN]
    _description = "Parameter Authorization"
    _order = "person_id, parameter_id"
    _permission_actions = ("create", "edit", "delete")

    if not TYPE_CHECKING:
        # The person authorized.
        person_id = fields.Many2one(MODEL_PERSON, required=True, ondelete="cascade")
        # The parameter the person may test.
        parameter_id = fields.Many2one(MODEL_TEST_PARAMETER, required=True, ondelete="cascade", index=True)

    _person_parameter_unique = models.Constraint(
        "UNIQUE(person_id, parameter_id)", "The person is already authorized to test this parameter."
    )

    @api.depends("person_id", "parameter_id")
    def _compute_display_name(self):
        for authorization in self:
            authorization.display_name = f"{authorization.person_id.name}: {authorization.parameter_id.name}"

    @api.model
    def _authorized(self, person, parameters):
        """True when the person may test every one of the parameters."""
        if not parameters:
            return True
        found = self.sudo().search_count(
            Domain("person_id", "=", person.id) & Domain("parameter_id", "in", parameters.ids)
        )
        return found == len(parameters)

    @api.model
    def _check_authorized(self, person, parameters):
        if not self._authorized(person, parameters):
            raise ValidationError(
                self.env._(
                    "%(person)s is not authorized to test %(parameter)s.",
                    person=person.sudo().name,
                    parameter=format_list(self.env, parameters.mapped("display_name")),
                )
            )
