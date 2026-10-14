from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .people_case import PeopleCase
from odoo.addons.sol_laboratory.constants.models import MODEL_PERMISSION, MODEL_PERSON, MODEL_ROLE


@tagged("post_install", "-at_install")
class TestOwnTeamScope(PeopleCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.pesticides = cls.create_team("Pesticide residues", cls.chemistry)
        cls.metals = cls.create_team("Heavy metals", cls.chemistry)
        cls.chemist.team_id = cls.pesticides
        cls.colleague = cls.create_person("Pham Thi Dung", cls.chemistry)
        cls.colleague.team_id = cls.pesticides
        cls.other_team = cls.create_person("Hoang Van Em", cls.chemistry)
        cls.other_team.team_id = cls.metals
        cls.lead = cls.create_person("Do Thi Giang", cls.chemistry, "giang.do", permissions=["person.read.own_team"])
        cls.lead.team_id = cls.pesticides
        cls.people = cls.as_person(cls.env[MODEL_PERSON], cls.lead)

    def test_only_people_of_the_own_team_are_listed(self):
        self.assertEqual(self.people.search([]), self.chemist | self.colleague | self.lead)

    def test_person_of_another_team_cannot_be_read(self):
        with self.assertRaises(AccessError):
            self.as_person(self.other_team, self.lead).read(["name"])

    def test_person_without_a_team_sees_nobody(self):
        self.lead.team_id = False

        self.assertFalse(self.people.search([]))

    def test_moving_to_another_team_moves_what_the_lead_sees(self):
        self.lead.team_id = self.metals

        self.assertEqual(self.people.search([]), self.other_team | self.lead)

    def test_editing_is_limited_to_the_own_team(self):
        self.grant(self.lead, "person.edit.own_team")

        self.as_person(self.colleague, self.lead).write({"phone": "0912 345 678"})
        self.assertEqual(self.colleague.phone, "0912 345 678")
        with self.assertRaises(AccessError):
            self.as_person(self.other_team, self.lead).write({"phone": "0912 345 678"})

    def test_own_team_needs_a_team_on_the_document_type(self):
        with self.assertRaises(ValidationError):
            self.env[MODEL_PERMISSION].create(
                {
                    "name": "Read roles of their team",
                    "document_model": MODEL_ROLE,
                    "action": "read",
                    "scope": "own_team",
                }
            )

    def test_own_team_access_limits_records_to_the_users_team(self):
        permission = self.env[MODEL_PERMISSION].new(
            {"document_model": MODEL_PERSON, "action": "read", "scope": "own_team"}
        )

        self.assertEqual(
            permission._access_values()["domain"],
            "[('team_id', 'in', user.employee_id.person_team_id.ids)]",
        )
