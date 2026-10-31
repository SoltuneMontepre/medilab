from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .people_case import PeopleCase
from odoo.addons.sol_laboratory.constants.departments import DEPARTMENT_DOMAIN
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_DEPARTMENT,
    MODEL_PARAMETER_METHOD,
    MODEL_PERSON,
    MODEL_TASK,
)
from odoo.addons.sol_laboratory.tests.assertions import assert_instance


@tagged("post_install", "-at_install")
class TestTeams(PeopleCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pesticides = cls.create_team("Pesticide residues", cls.chemistry)
        cls.metals = cls.create_team("Heavy metals", cls.chemistry)
        cls.pathogens = cls.create_team("Pathogens", cls.microbiology)

    def test_a_person_joins_a_team_of_their_department(self):
        self.chemist.team_id = self.pesticides

        self.assertEqual(self.chemist.team_id, self.pesticides)
        self.assertEqual(self.pesticides.team_person_ids, self.chemist)

    def test_a_team_of_another_department_is_refused(self):
        with self.assertRaises(ValidationError):
            self.chemist.team_id = self.pathogens
        with self.assertRaises(ValidationError):
            self.env[MODEL_PERSON].create(
                {"name": "Vu Van Hai", "department_id": self.chemistry.id, "team_id": self.pathogens.id}
            )

    def test_a_department_is_not_a_team(self):
        with self.assertRaises(ValidationError):
            self.chemist.team_id = self.microbiology

    def test_moving_to_another_department_leaves_the_team(self):
        self.chemist.team_id = self.pesticides

        self.chemist.employee_id.department_id = self.microbiology

        self.assertFalse(self.chemist.team_id)

    def test_moving_to_another_department_with_one_of_its_teams(self):
        self.chemist.team_id = self.pesticides

        self.chemist.write({"department_id": self.microbiology.id, "team_id": self.pathogens.id})

        self.assertEqual(self.chemist.team_id, self.pathogens)

    def test_a_department_and_a_team_of_another_department_are_refused_together(self):
        with self.assertRaises(ValidationError):
            self.chemist.write({"department_id": self.microbiology.id, "team_id": self.pesticides.id})

    def test_a_team_with_people_keeps_its_department(self):
        self.chemist.team_id = self.pesticides

        for parent in (self.microbiology, self.env[MODEL_DEPARTMENT]):
            with self.subTest(parent=parent.name), self.assertRaises(ValidationError):
                self.pesticides.parent_id = parent

    def test_a_department_named_by_people_cannot_become_a_team(self):
        department = self.env[MODEL_DEPARTMENT].create({"name": "Physics"})
        self.create_person("Vu Van Hai", department)

        with self.assertRaises(ValidationError):
            department.parent_id = self.chemistry

    def test_a_team_with_no_people_can_be_deleted(self):
        self.metals.unlink()

        self.assertFalse(self.metals.exists())

    def test_a_team_with_people_cannot_be_deleted(self):
        self.chemist.team_id = self.pesticides

        with self.assertRaises(UserError) as refusal:
            self.pesticides.unlink()

        self.assertIn(self.chemist.name, str(refusal.exception))

    def test_a_department_with_teams_cannot_be_deleted(self):
        department = self.env[MODEL_DEPARTMENT].create({"name": "Physics"})
        team = self.create_team("Radioactivity", department)

        with self.assertRaises(UserError) as refusal:
            department.unlink()

        self.assertEqual(str(refusal.exception).count(assert_instance(team.name, str)), 1)

    def test_a_team_has_no_teams_of_its_own(self):
        with self.assertRaises(ValidationError):
            self.create_team("Organophosphates", self.pesticides)

    def test_a_department_with_teams_cannot_become_a_team(self):
        with self.assertRaises(ValidationError):
            self.chemistry.parent_id = self.microbiology

    def test_teams_are_left_out_of_department_choices(self):
        for model_name in (MODEL_PERSON, MODEL_PARAMETER_METHOD, MODEL_TASK, MODEL_DEPARTMENT):
            field_name = "parent_id" if model_name == MODEL_DEPARTMENT else "department_id"
            with self.subTest(model=model_name):
                self.assertEqual(
                    assert_instance(self.env[model_name]._fields[field_name], fields.Many2one).domain, DEPARTMENT_DOMAIN
                )
