from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import MasterDataCase
from odoo.addons.laboratory.constants.models import MODEL_PARAMETER_GROUP, MODEL_SAMPLE_TYPE, MODEL_TEST_PARAMETER


@tagged("post_install", "-at_install")
class TestTreeFilters(MasterDataCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pesticides = cls.env[MODEL_PARAMETER_GROUP].create({"name": "Pesticides"})
        cls.organophosphates = cls.env[MODEL_PARAMETER_GROUP].create(
            {"name": "Organophosphates", "parent_id": cls.pesticides.id}
        )
        cls.food = cls.env[MODEL_SAMPLE_TYPE].create({"name": "Food"})
        cls.vegetables = cls.env[MODEL_SAMPLE_TYPE].create({"name": "Vegetables", "parent_id": cls.food.id})
        cls.cabbage = cls.env[MODEL_SAMPLE_TYPE].create({"name": "Cabbage", "parent_id": cls.vegetables.id})
        cls.chlorpyrifos = cls.create_parameter("Chlorpyrifos", cls.organophosphates, sample_type_ids=[cls.cabbage.id])

    def test_parameter_of_sub_group_is_found_by_parent_group(self):
        found = self.env[MODEL_TEST_PARAMETER].search([("group_ids", "child_of", self.pesticides.id)])

        self.assertEqual(found, self.chlorpyrifos)

    def test_parameter_of_narrower_sample_type_is_found_by_broader_type(self):
        found = self.env[MODEL_TEST_PARAMETER].search([("sample_type_ids", "child_of", self.vegetables.id)])

        self.assertEqual(found, self.chlorpyrifos)

    def test_group_cannot_be_its_own_ancestor(self):
        for parent in (self.pesticides, self.organophosphates):
            with self.subTest(parent=parent.name), self.assertRaises(UserError):
                self.pesticides.parent_id = parent

    def test_sample_type_cannot_be_its_own_ancestor(self):
        for parent in (self.food, self.cabbage):
            with self.subTest(parent=parent.name), self.assertRaises(UserError):
                self.food.parent_id = parent
