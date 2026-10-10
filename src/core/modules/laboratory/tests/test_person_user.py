from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from .people_case import PeopleCase
from odoo.addons.laboratory.constants.models import MODEL_DEPARTMENT, MODEL_PERSON, MODEL_ROLE


@tagged("post_install", "-at_install")
class TestPersonUser(PeopleCase):
    def test_login_creates_an_internal_user_on_the_persons_contact(self):
        user = self.chemist.user_id

        self.assertEqual(user.partner_id, self.chemist.partner_id)
        self.assertEqual(self.chemist.login, user.login)
        self.assertEqual(user.login, "an.nguyen")
        self.assertTrue(user._is_internal())

    def test_details_are_kept_on_the_contact(self):
        self.chemist.write({"name": "Nguyen Van Anh", "email": "anh.nguyen@lab.example", "phone": "0901 234 567"})

        partner = self.chemist.partner_id
        self.assertEqual(
            (partner.name, partner.email, partner.phone), ("Nguyen Van Anh", "anh.nguyen@lab.example", "0901 234 567")
        )

    def test_person_without_login_has_no_user(self):
        person = self.create_person("Le Van Cuong", self.chemistry)

        self.assertFalse(person.user_id)

    def test_user_holds_the_groups_of_roles_and_direct_permissions(self):
        role = self.env[MODEL_ROLE].create(
            {
                "code": "reader",
                "name": "Reader",
                "permission_ids": [Command.set(self.permissions("department.read.all").ids)],
            }
        )
        export = self.env.ref("base.group_allow_export")
        user = self.chemist.user_id
        user.group_ids = [Command.link(export.id)]

        self.chemist.write({"role_ids": [Command.set(role.ids)]})
        self.grant(self.chemist, "person.read.all")
        self.assertTrue({role.group_id, self.permissions("person.read.all").group_id, export} <= set(user.group_ids))

        self.chemist.write({"role_ids": [Command.clear()], "permission_ids": [Command.clear()]})
        self.assertEqual(user.group_ids, self.env.ref("base.group_user") | export)

    def test_direct_permission_adds_to_the_permissions_of_roles(self):
        role = self.env[MODEL_ROLE].create(
            {
                "code": "reader",
                "name": "Reader",
                "permission_ids": [Command.set(self.permissions("department.read.all").ids)],
            }
        )
        self.chemist.role_ids = role
        self.grant(self.chemist, "department.edit.all")

        self.as_person(self.chemistry, self.chemist).write({"name": "Analytical chemistry"})

        self.assertEqual(self.chemistry.name, "Analytical chemistry")

    def test_changing_the_user_takes_the_groups_off_the_previous_one(self):
        self.grant(self.chemist, "person.read.all")
        previous = self.chemist.user_id
        newcomer = self.env["res.users"].create({"login": "an.nguyen.2", "name": "Nguyen Van An"})

        self.chemist.user_id = newcomer

        self.assertNotIn(self.permissions("person.read.all").group_id, previous.group_ids)
        self.assertIn(self.permissions("person.read.all").group_id, newcomer.group_ids)

    def test_archiving_a_person_archives_their_user(self):
        self.chemist.action_archive()
        self.assertFalse(self.chemist.user_id.active)

        self.chemist.action_unarchive()
        self.assertTrue(self.chemist.user_id.active)

    def test_deleting_a_person_takes_their_groups_off_the_user(self):
        self.grant(self.chemist, "person.read.all")
        user = self.chemist.user_id

        self.chemist.unlink()

        self.assertEqual(user.group_ids, self.env.ref("base.group_user"))

    def test_people_of_a_department_are_listed_on_it(self):
        self.assertEqual(self.env[MODEL_DEPARTMENT].browse(self.chemistry.id).person_ids, self.chemist)
        self.assertEqual(
            self.env[MODEL_PERSON].search([("department_id", "=", self.microbiology.id)]), self.microbiologist
        )

    def test_login_of_a_person_who_signs_in_cannot_be_emptied(self):
        with self.assertRaises(UserError):
            self.chemist.write({"login": False})

        self.assertEqual(self.chemist.user_id.login, "an.nguyen")

    def test_one_login_cannot_be_given_to_several_people(self):
        newcomers = self.create_person("Le Van Cuong") | self.create_person("Pham Thi Dung")

        with self.assertRaises(UserError):
            newcomers.write({"login": "shared.login"})
