from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import MODEL_DEPARTMENT, MODEL_SUBCONTRACTOR


@tagged("post_install", "-at_install")
class TestParameterMethodDepartment(MasterDataCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.chemistry = cls.env[MODEL_DEPARTMENT].create({"name": "Chemistry"})

    def test_department_can_be_named_on_an_in_house_way_of_testing(self):
        self.pair.department_id = self.chemistry

        self.assertEqual(self.pair.department_id, self.chemistry)

    def test_way_of_testing_is_not_both_in_house_and_subcontracted(self):
        subcontractor = self.env[MODEL_SUBCONTRACTOR].create({"name": "Northern Testing Laboratory"})

        with self.assertRaises(ValidationError):
            self.pair.write({"department_id": self.chemistry.id, "subcontractor_id": subcontractor.id})

    def test_department_testing_a_way_of_testing_cannot_be_archived_or_deleted(self):
        self.pair.department_id = self.chemistry

        for action in (self.chemistry.action_archive, self.chemistry.unlink):
            with self.subTest(action=action.__name__), self.assertRaises(UserError) as refusal:
                action()
            self.assertIn(self.pair.display_name, str(refusal.exception))

    def test_department_of_an_archived_way_of_testing_can_be_archived_but_not_deleted(self):
        self.pair.department_id = self.chemistry
        self.pair.action_archive()

        self.chemistry.action_archive()

        self.assertFalse(self.chemistry.active)
        with self.assertRaises(UserError):
            self.chemistry.unlink()
