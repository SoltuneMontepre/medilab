from odoo import fields, models

from odoo.addons.sol_laboratory.constants.models import MODEL_DEPARTMENT, MODEL_EMPLOYEE, MODEL_PERSON


# Nhân Viên
class HrEmployee(models.Model):
    _inherit = MODEL_EMPLOYEE

    # Employee name, searched with the person.
    name = fields.Char(index="trigram")
    # Work email, searched with the person.
    work_email = fields.Char(index="trigram")
    # Team of the employee's person, which own-team accesses read from the user's employee.
    person_team_id = fields.Many2one(MODEL_DEPARTMENT, compute="_compute_person_team_id", compute_sudo=True)

    def _compute_person_team_id(self):
        teams = {person.employee_id.id: person.team_id for person in self._people()}
        for employee in self:
            employee.person_team_id = teams.get(employee.id, False)

    def write(self, vals):
        # Odoo's Employees app changes employees too, so the person's rules and groups follow from here.
        people = self._people() if {"user_id", "active", "department_id"} & set(vals) else self.env[MODEL_PERSON]
        people._check_administrator_change(vals)
        previous_users = self.sudo().user_id
        result = super().write(vals)
        if "department_id" in vals and not self.env.context.get("keep_person_team"):
            # A person who moves to another department leaves their team.
            people._outside_their_department().team_id = False
        if "name" in vals:
            # Odoo keeps the work contact's email and phone in step with the employee, but not its name.
            contacts = self.sudo().work_contact_id.filtered(lambda contact: len(contact.employee_ids) <= 1)
            contacts.write({"name": vals["name"]})
        if "user_id" in vals:
            people._strip_user_groups(previous_users - self.sudo().user_id)
            people._sync_user_groups()
        if "active" in vals:
            people.filtered(lambda person: person.active != vals["active"]).with_env(self.env).write(
                {"active": vals["active"]}
            )
        if {"department_id", "user_id"} & set(vals) and (previous_users or self.sudo().user_id):
            # Own-department accesses are evaluated from the user's employee and cached per user.
            self.env.transaction.invalidate_ormcache()
        return result

    def unlink(self):
        # Deleting an employee deletes its person, whose permission and rules apply first.
        self._people().with_env(self.env).unlink()
        return super().unlink()

    def _people(self):
        return self.env[MODEL_PERSON].sudo().with_context(active_test=False).search([("employee_id", "in", self.ids)])
