from psycopg2 import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.sol_inventory.constants.models import MODEL_ANALYTIC_ACCOUNT
from odoo.addons.sol_inventory.constants.xml_ids import COST_CENTRE_PLAN
from odoo.addons.sol_laboratory.tests.people_case import PeopleCase


@tagged("post_install", "-at_install")
class TestCostCentres(PeopleCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pesticides = cls.create_team("Pesticides", cls.chemistry)
        cls.chemistry_centre = cls.create_cost_centre("Chemistry", "TEST-HH", cls.chemistry)

    @classmethod
    def create_cost_centre(cls, name, code, department):
        return cls.env[MODEL_ANALYTIC_ACCOUNT].create(
            {
                "name": name,
                "code": code,
                "department_id": department.id,
                "plan_id": cls.env.ref(COST_CENTRE_PLAN).id,
            }
        )

    def test_a_department_and_a_team_each_have_their_cost_centre(self):
        team_centre = self.create_cost_centre("Pesticides", "TEST-HH-TBVTV", self.pesticides)

        self.assertEqual((team_centre.department_id, team_centre.code), (self.pesticides, "TEST-HH-TBVTV"))

    def test_two_cost_centres_with_the_same_code_are_refused(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.create_cost_centre("Food microbiology", "TEST-HH", self.microbiology)

    def test_a_department_has_one_cost_centre(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.create_cost_centre("Chemistry, second code", "TEST-HH2", self.chemistry)

    def test_a_cost_centre_needs_a_code_and_a_department(self):
        plan = self.env.ref(COST_CENTRE_PLAN)
        for vals in ({"code": "TEST-VS"}, {"department_id": self.microbiology.id}):
            with self.subTest(vals=vals), self.assertRaises(ValidationError):
                self.env[MODEL_ANALYTIC_ACCOUNT].create({"name": "Food microbiology", "plan_id": plan.id, **vals})
