from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.sol_laboratory.constants.models import MODEL_PERSON, MODEL_RES_USERS, MODEL_USER_LINK


# Gắn Tài Khoản Với Nhân Sự
class UserLink(models.TransientModel):
    _name = MODEL_USER_LINK
    _description = "Link a User to a Person"

    # The internal user no person links to.
    user_id = fields.Many2one(MODEL_RES_USERS, required=True, ondelete="cascade", domain=[("share", "=", False)])
    # The person who signs in as the user from now on; empty to create a person from the user.
    person_id = fields.Many2one(MODEL_PERSON, domain=[("user_id", "=", False)])

    def action_link(self):
        self.ensure_one()
        user = self.user_id
        if user.has_person:
            raise UserError(self.env._("%s is already linked to a person.", user.name))
        if self.person_id:
            person = self._link_person()
        else:
            # A person created for a user who already has an employee delegates to that employee.
            person = self.env[MODEL_PERSON].create({"name": user.name, "user_id": user.id})
        # The flag was read above, before the person took the user.
        user.invalidate_recordset(["has_person"])
        return person._get_records_action()

    def _link_person(self):
        user = self.user_id
        person = self.person_id
        if person.user_id:
            raise UserError(self.env._("%s already signs in as another user.", person.name))
        employee = user.sudo().with_context(active_test=False).employee_ids - person.sudo().employee_id
        if employee:
            raise UserError(
                self.env._(
                    "%(user)s already has the employee %(employee)s; leave the person empty to create a person from "
                    "that employee.",
                    user=user.name,
                    employee=employee[:1].name,
                )
            )
        person.user_id = user
        return person
