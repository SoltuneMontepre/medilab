from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST, MODEL_TASK
from odoo.addons.sol_laboratory.constants.tasks import TESTING_ACTION

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_sample_test as SampleTestClaimBase
else:
    SampleTestClaimBase = object


# Chỉ Tiêu Của Mẫu: the sample test's testing task, as the current person sees it on the test, and claiming it there.
class SampleTestClaim(models.Model, SampleTestClaimBase):
    _inherit = MODEL_SAMPLE_TEST

    if not TYPE_CHECKING:
        # True when the test's testing task is assigned to the current person.
        is_mine = fields.Boolean(string="Mine", compute="_compute_testing_task_state", search="_search_is_mine")
        # True when the test's testing task waits in a queue the current person can claim from.
        can_claim = fields.Boolean(compute="_compute_testing_task_state", search="_search_can_claim")
        # Where the tested sample is kept, so the tester knows where to fetch it.
        storage_location = fields.Char(related="sample_id.storage_location")

    @api.depends_context("uid")
    def _compute_testing_task_state(self):
        tests = self.filtered("id")
        tasks = self.env[MODEL_TASK]._system_tasks_of(tests, TESTING_ACTION)
        task_of = {task.document_id: task for task in tasks}
        for test in self:
            task = task_of.get(test.id)
            test.is_mine = bool(task and task.is_mine)
            test.can_claim = bool(task and task.in_my_queue)

    def _search_is_mine(self, operator, value):
        return self._search_by_testing_task(operator, value, "is_mine")

    def _search_can_claim(self, operator, value):
        return self._search_by_testing_task(operator, value, "in_my_queue")

    def _search_by_testing_task(self, operator, value, task_field):
        if operator != "in" or True not in value:
            return NotImplemented
        task_model = self.env[MODEL_TASK].sudo()
        domain = task_model._system_tasks_domain(self._name, TESTING_ACTION) & Domain(task_field, "=", True)
        tasks = task_model.search(domain)
        return Domain("id", "in", tasks.mapped("document_id"))

    def action_claim_testing_task(self):
        tasks = self.env[MODEL_TASK]
        for test in self:
            task = test._testing_task()
            if not task:
                raise UserError(self.env._("%s has no testing task to claim.", test.display_name))
            tasks |= task
        tasks.with_env(self.env).action_claim()
