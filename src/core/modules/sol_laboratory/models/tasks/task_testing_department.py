from typing import TYPE_CHECKING

from odoo import api, models
from odoo.exceptions import ValidationError

from odoo.addons.sol_laboratory.constants.models import MODEL_DEPARTMENT, MODEL_SAMPLE_TEST, MODEL_TASK
from odoo.addons.sol_laboratory.constants.tasks import FINAL_STATUSES

if TYPE_CHECKING:
    from medilab_model_types import Model_medilab_task as TaskTestingDepartmentBase
else:
    TaskTestingDepartmentBase = object


# Nhiệm Vụ: a testing task stays in the department of its test's way of testing.
class TaskTestingDepartment(models.Model, TaskTestingDepartmentBase):
    _inherit = MODEL_TASK

    def _way_department(self):
        """The department that tests a testing task's sample test by its way of testing; empty for any other task."""
        self.ensure_one()
        if not self.sudo().filtered_domain(self._testing_domain()):
            return self.env[MODEL_DEPARTMENT]
        test = self.env[MODEL_SAMPLE_TEST].sudo().browse(self.document_id).exists()
        if not test:
            return self.env[MODEL_DEPARTMENT]
        return test.sample_id._department_by_test()[test]

    def _way_departments(self):
        """The departments that test the testing tasks among the tasks."""
        return self.env[MODEL_DEPARTMENT].union(task._way_department() for task in self)

    @api.constrains("department_id")
    def _check_way_department(self):
        for task in self.filtered(lambda task: task.status not in FINAL_STATUSES):
            department = task._way_department()
            if department and task.department_id != department:
                raise ValidationError(
                    self.env._(
                        "%(task)s is tested by %(department)s and cannot move to another department.",
                        task=task.name,
                        department=department.name,
                    )
                )
