from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import MasterDataCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_PARAMETER_GROUP,
    MODEL_PARAMETER_METHOD,
    MODEL_SAMPLE_TYPE,
    MODEL_TEST_PARAMETER,
    MODEL_TESTING_METHOD,
)


@tagged("post_install", "-at_install")
class TestParameterConstraints(MasterDataCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.icp_ms = cls.env[MODEL_TESTING_METHOD].create(
            {"code": "ISO 15586:2003", "name": "ICP-MS", "field_id": cls.testing_field.id}
        )

    def test_code_is_unique(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.create_parameter("Duplicate", self.group, code=self.parameter.code)

    def test_parameters_are_ordered_by_code(self):
        self.create_parameter("Red blood cells", self.group, code="RBC")
        self.create_parameter("Hemoglobin", self.group, code="HGB")

        codes = self.env[MODEL_TEST_PARAMETER].search([("code", "in", ["RBC", "HGB"])]).mapped("code")

        self.assertEqual(codes, ["HGB", "RBC"])

    def test_parameter_cannot_join_group_with_sub_groups(self):
        pesticides = self.env[MODEL_PARAMETER_GROUP].create({"name": "Pesticides"})
        self.env[MODEL_PARAMETER_GROUP].create({"name": "Organophosphates", "parent_id": pesticides.id})

        with self.assertRaises(ValidationError):
            self.create_parameter("Glyphosate", pesticides)

    def test_group_with_parameters_cannot_get_sub_groups(self):
        with self.assertRaises(ValidationError):
            self.env[MODEL_PARAMETER_GROUP].create({"name": "Lead compounds", "parent_id": self.group.id})

    def test_group_side_changes_follow_the_same_rules(self):
        pesticides = self.env[MODEL_PARAMETER_GROUP].create({"name": "Pesticides"})
        self.env[MODEL_PARAMETER_GROUP].create({"name": "Organophosphates", "parent_id": pesticides.id})

        for group, command in ((pesticides, (4, self.parameter.id)), (self.group, (3, self.parameter.id))):
            with self.subTest(group=group.name), self.assertRaises(ValidationError):
                group.write({"parameter_ids": [command]})

    def test_main_group_must_be_one_of_the_groups(self):
        other_group = self.env[MODEL_PARAMETER_GROUP].create({"name": "Microbiology"})

        with self.assertRaises(ValidationError):
            self.parameter.main_group_id = other_group

    def test_parameter_keeps_several_methods_groups_and_sample_types(self):
        groups = self.env[MODEL_PARAMETER_GROUP].create([{"name": "Metals"}, {"name": "Drinking water"}])
        sample_types = self.env[MODEL_SAMPLE_TYPE].create([{"name": "Bottled water"}, {"name": "Cabbage"}])

        parameter = self.create_parameter(
            "Cadmium (Cd)",
            groups[0],
            group_ids=groups.ids,
            method_ids=[
                Command.create({"method_id": self.method.id, "department_id": self.department.id}),
                Command.create({"method_id": self.icp_ms.id, "department_id": self.department.id}),
            ],
        )
        for sample_type in sample_types:
            self.offer(parameter, sample_type)

        self.assertEqual(parameter.group_ids, groups)
        self.assertEqual(parameter.sample_type_ids, sample_types)
        self.assertEqual(parameter.method_ids.method_id, self.method | self.icp_ms)

    def test_an_in_house_way_of_testing_without_a_department_is_refused(self):
        with self.assertRaisesRegex(ValidationError, "needs the department that tests it, or a subcontractor"):
            self.env[MODEL_PARAMETER_METHOD].create({"parameter_id": self.parameter.id, "method_id": self.icp_ms.id})

    def test_a_way_of_testing_cannot_lose_its_department(self):
        with self.assertRaisesRegex(ValidationError, "needs the department that tests it, or a subcontractor"):
            self.pair.department_id = False
