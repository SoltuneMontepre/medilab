from pathlib import Path

from freezegun import freeze_time

from odoo.modules.module import load_script
from odoo.tests import tagged

from .dispatch_case import DispatchCase
from .scheduling_case import MONDAY
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST

POST_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.55.0" / "post-migrate.py"


@freeze_time(MONDAY)
@tagged("post_install", "-at_install")
class TestOutsourcedTaskMigration(DispatchCase):
    """The lead test was outsourced before outsourcing ended its testing task, which is still assigned to the tester;
    another lead test of the sample is tested in the laboratory."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.as_person(cls.test, cls.head)._accept_outsourcing(cls.northern_way)
        cls.task.write({"status": "assigned"})
        cls.in_house = cls.env[MODEL_SAMPLE_TEST].create({"sample_id": cls.sample.id, "parameter_id": cls.parameter.id})
        cls.in_house_task = cls.testing_task(cls.in_house, cls.tester)

    def migrate(self):
        load_script(str(POST_MIGRATE), "post_migrate").migrate(self.env.cr, "20.0.1.54.0")
        self.env.invalidate_all()

    def test_the_open_testing_task_of_an_outsourced_test_is_cancelled(self):
        self.migrate()

        self.assertEqual(self.task.status, "cancelled")
        self.assertEqual(self.test._tested_by(), self.department)

    def test_the_testing_task_of_a_test_in_the_laboratory_stays_assigned(self):
        self.migrate()

        self.assertEqual(self.in_house_task.status, "assigned")
