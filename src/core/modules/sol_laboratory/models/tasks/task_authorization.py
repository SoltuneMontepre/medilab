from typing import TYPE_CHECKING

from odoo import api, models
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import (
    MODEL_PARAMETER_AUTHORIZATION,
    MODEL_PERSON,
    MODEL_SAMPLE_TEST,
    MODEL_TASK,
    MODEL_TEST_PARAMETER,
)

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_task as TaskAuthorizationBase
else:
    TaskAuthorizationBase = object


# Nhiệm Vụ: a testing task goes only to a person the Lab Head authorized to test its parameter.
class TaskAuthorization(models.Model, TaskAuthorizationBase):
    _inherit = MODEL_TASK

    def _parameter(self):
        """The parameter of a testing task's sample test; empty for any other task."""
        self.ensure_one()
        if not self.sudo().filtered_domain(self._testing_domain()):
            return self.env[MODEL_TEST_PARAMETER]
        return self.env[MODEL_SAMPLE_TEST].sudo().browse(self.document_id).parameter_id

    @api.constrains("assignee_id")
    def _check_assignee_authorized(self):
        for task in self.filtered("assignee_id"):
            self.env[MODEL_PARAMETER_AUTHORIZATION]._check_authorized(task.assignee_id, task._parameter())

    def action_claim(self):
        # Checked before the claim locks the task, so an unauthorized claim never keeps someone else from claiming it.
        person = self.env[MODEL_PERSON]._current()
        for task in self.sudo().filtered(lambda task: task._claimable_by(person)):
            self.env[MODEL_PARAMETER_AUTHORIZATION]._check_authorized(person, task._parameter())
        return super().action_claim()

    def _compute_in_my_queue(self):
        result = super()._compute_in_my_queue()
        person = self.env[MODEL_PERSON]._current()
        authorizations = self.env[MODEL_PARAMETER_AUTHORIZATION]
        for task in self.filtered("in_my_queue"):
            task.in_my_queue = authorizations._authorized(person, task._parameter())
        return result

    def _search_in_my_queue(self, operator, value):
        domain = super()._search_in_my_queue(operator, value)
        person = self.env[MODEL_PERSON]._current()
        if domain is NotImplemented or not person:
            return domain
        authorized = self.env[MODEL_PARAMETER_AUTHORIZATION].sudo().search(Domain("person_id", "=", person.id))
        tests = self.env[MODEL_SAMPLE_TEST].sudo()._search(Domain("parameter_id", "in", authorized.parameter_id.ids))
        return domain & (~self._testing_domain() | Domain("document_id", "in", tests))
