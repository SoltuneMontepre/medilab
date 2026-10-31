from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import format_list

from odoo.addons.sol_laboratory.constants.models import MODEL_PERSON, MODEL_RES_USERS


# Tài Khoản: internal users are created and made internal only through people.
class ResUsers(models.Model):
    _inherit = MODEL_RES_USERS

    # Whether a person signs in as the user, archived people included.
    has_person = fields.Boolean(compute="_compute_has_person", search="_search_has_person")

    def _compute_has_person(self):
        linked = set(self._linked_user_ids())
        for user in self:
            user.has_person = user.id in linked

    def _search_has_person(self, operator, value):
        # Odoo rewrites a boolean comparison as "in" or "not in" {True} before calling a search method.
        if operator not in ("in", "not in") or True not in value:
            return NotImplemented
        linked = Domain("id", "in", self._linked_user_ids())
        return linked if operator == "in" else ~linked

    def _linked_user_ids(self):
        people = self.env[MODEL_PERSON].sudo().with_context(active_test=False)
        return people.search([("user_id", "!=", False)]).user_id.ids

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users._check_internal_through_person()
        return users

    def write(self, vals):
        shared = self.filtered("share")
        result = super().write(vals)
        shared._check_internal_through_person()
        return result

    def _check_internal_through_person(self):
        # A person creates and promotes its user with full rights; what an administrator calls, also through RPC,
        # runs with their own.
        if self.env.su:
            return
        internal = self.filtered(lambda user: not user.share)
        if internal:
            raise UserError(
                self.env._(
                    "%s can be an internal user only through a person: give a person a login, or link the user to "
                    "a person from Unlinked Users.",
                    format_list(self.env, internal.mapped("name")),
                )
            )
