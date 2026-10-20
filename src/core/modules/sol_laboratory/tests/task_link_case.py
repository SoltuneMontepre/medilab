from datetime import timedelta

from .scheduling_case import MONDAY, SchedulingCase
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST, MODEL_TASK, MODEL_TESTING_METHOD_STEP
from odoo.addons.sol_laboratory.constants.tasks import TESTING_ACTION


class TaskLinkCase(SchedulingCase):
    """A person who creates and edits every task but reads no sample test, and a test whose method has a step."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.planner = cls.create_person(
            "Bui Van Hung",
            cls.department,
            "hung.bui",
            permissions=("task.read.all", "task.create.all", "task.edit.all"),
        )
        cls.env[MODEL_TESTING_METHOD_STEP].create(
            {"method_id": cls.method.id, "sequence": 1, "duration_minutes": 15, "instruction": "Weigh the sample."}
        )
        cls.test.parameter_method_id = cls.pair
        cls.general = cls.env.ref("sol_laboratory.task_type_general")
        cls.testing_type = cls.env.ref("sol_laboratory.task_type_sample_test")

    def hand_task(self, **vals):
        return self.as_person(self.env[MODEL_TASK], self.planner).create(
            {
                "type_id": self.general.id,
                "name": "Check the balance",
                "assignee_id": self.planner.id,
                "deadline": MONDAY + timedelta(days=1),
                **vals,
            }
        )

    def legacy_task(self, department, retype=False):
        """A task made by hand and linked to the test before links were locked, stored as the upgrade leaves it: not
        linked by the system. With retype, it was then changed to the testing type, as anyone could do."""
        task = self.env[MODEL_TASK].create(
            {
                "type_id": self.general.id,
                "name": "Check the balance",
                "assignee_id": self.planner.id,
                "department_id": department.id,
                "deadline": MONDAY + timedelta(days=1),
                "document_model": MODEL_SAMPLE_TEST,
                "document_id": self.test.id,
                "action": TESTING_ACTION,
                "linked_by_system": False,
            }
        )
        if retype:
            task.write({"type_id": self.testing_type.id})
        return task
