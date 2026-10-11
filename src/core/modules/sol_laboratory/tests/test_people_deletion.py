from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from .people_case import PeopleCase
from odoo.addons.sol_laboratory.constants.models import MODEL_DEPARTMENT, MODEL_ROLE


@tagged("post_install", "-at_install")
class TestPeopleDeletion(PeopleCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tester = cls.env[MODEL_ROLE].create({"code": "qa_tester", "name": "Tester"})
        cls.chemist.role_ids = cls.tester

    def test_role_held_by_a_person_cannot_be_deleted(self):
        with self.assertRaises(UserError) as refusal:
            self.tester.unlink()

        self.assertIn(self.chemist.name, str(refusal.exception))

    def test_role_removed_from_people_can_be_deleted(self):
        self.chemist.role_ids = [Command.unlink(self.tester.id)]

        self.tester.unlink()

        self.assertFalse(self.tester.exists())

    def test_department_with_people_cannot_be_archived_or_deleted(self):
        for action in (self.chemistry.action_archive, self.chemistry.unlink):
            with self.subTest(action=action.__name__), self.assertRaises(UserError) as refusal:
                action()
            self.assertIn(self.chemist.name, str(refusal.exception))

    def test_department_person_and_role_nothing_refers_to_can_be_deleted(self):
        department = self.env[MODEL_DEPARTMENT].create({"name": "Sample reception"})
        person = self.create_person("Le Van Cuong")
        role = self.env[MODEL_ROLE].create({"code": "qa_storekeeper", "name": "Storekeeper"})

        department.unlink()
        person.unlink()
        role.unlink()

        self.assertFalse(department.exists() or person.exists() or role.exists())

    def test_deleting_a_person_removes_them_from_their_roles(self):
        self.chemist.unlink()

        self.assertFalse(self.tester.person_ids)

    def test_a_hidden_referrer_blocks_archiving_without_being_named(self):
        reader = self.create_person(
            "Do Thi Giang",
            self.chemistry,
            "giang.do",
            permissions=["department.read.all", "department.archive.all", "person.read.own_department"],
        )
        colleague = self.create_person("Pham Thi Dung", self.microbiology)

        with self.assertRaises(UserError) as refusal:
            self.as_person(self.microbiology, reader).action_archive()

        message = str(refusal.exception)
        self.assertNotIn(self.microbiologist.name, message)
        self.assertNotIn(colleague.name, message)
        self.assertIn("2 more", message)
        self.assertTrue(self.microbiology.active)
        with self.assertRaises(UserError) as refusal:
            self.as_person(self.chemistry, reader).action_archive()
        self.assertIn(self.chemist.name, str(refusal.exception))
