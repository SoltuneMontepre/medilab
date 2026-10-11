from odoo.exceptions import AccessError
from odoo.tests import tagged

from .people_case import PeopleCase
from odoo.addons.sol_laboratory.constants.models import MODEL_PERSON


@tagged("post_install", "-at_install")
class TestOwnDepartmentScope(PeopleCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.colleague = cls.create_person("Pham Thi Dung", cls.chemistry)
        cls.unassigned = cls.create_person("Hoang Van Em")
        cls.head = cls.create_person(
            "Do Thi Giang", cls.chemistry, "giang.do", permissions=["person.read.own_department"]
        )
        cls.people = cls.as_person(cls.env[MODEL_PERSON], cls.head)

    def test_only_people_of_the_own_department_are_listed(self):
        self.assertEqual(self.people.search([]), self.chemist | self.colleague | self.head)

    def test_person_of_another_department_cannot_be_read(self):
        with self.assertRaises(AccessError):
            self.as_person(self.microbiologist, self.head).read(["name"])

    def test_person_without_a_department_is_hidden(self):
        self.assertNotIn(self.unassigned, self.people.search([]))

    def test_editing_is_limited_to_the_own_department(self):
        self.grant(self.head, "person.edit.own_department")

        self.as_person(self.colleague, self.head).write({"phone": "0912 345 678"})
        self.assertEqual(self.colleague.phone, "0912 345 678")
        with self.assertRaises(AccessError):
            self.as_person(self.microbiologist, self.head).write({"phone": "0912 345 678"})

    def test_creating_is_limited_to_the_own_department(self):
        self.grant(self.head, "person.create.own_department")

        newcomer = self.people.create({"name": "Vu Van Hai", "department_id": self.chemistry.id})
        self.assertEqual(newcomer.department_id, self.chemistry)
        with self.assertRaises(AccessError):
            self.people.create({"name": "Bui Thi Lan", "department_id": self.microbiology.id})

    def test_archiving_stays_within_its_own_scope_when_editing_has_a_wider_one(self):
        self.grant(self.head, "person.read.all", "person.edit.all", "person.archive.own_department")

        self.as_person(self.colleague, self.head).action_archive()
        self.assertFalse(self.colleague.active)
        with self.assertRaises(AccessError):
            self.as_person(self.microbiologist, self.head).action_archive()
        self.assertTrue(self.microbiologist.active)

    def test_reading_every_person_shows_all_departments(self):
        self.grant(self.head, "person.read.all")

        self.assertTrue(self.chemist | self.microbiologist | self.unassigned <= self.people.search([]))
