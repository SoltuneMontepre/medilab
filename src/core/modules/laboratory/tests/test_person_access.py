from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import tagged

from .people_case import PeopleCase
from odoo.addons.laboratory.constants.models import MODEL_PERSON


@tagged("post_install", "-at_install")
class TestPersonAccess(PeopleCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.head = cls.create_person(
            "Do Thi Giang",
            cls.chemistry,
            "giang.do",
            permissions=["person.read.own_department", "person.edit.own_department"],
        )
        cls.lab_head = cls.create_person(
            "Ngo Van Khoa", cls.chemistry, permissions=["person.read.all", "person.edit.all", "department.read.all"]
        )

    def test_person_without_permission_cannot_read_people_or_see_the_screen(self):
        people = self.as_person(self.env[MODEL_PERSON], self.chemist)

        with self.assertRaises(AccessError):
            people.search([])
        with self.assertRaises(AccessError):
            people.get_views([(False, "form")])

    def test_person_editor_cannot_move_their_user_onto_a_stronger_person(self):
        own = self.as_person(self.head, self.head)
        stronger = self.as_person(self.lab_head, self.head)

        with self.assertRaises(AccessError):
            own.write({"user_id": False})
        with self.assertRaises(AccessError):
            stronger.write({"user_id": self.head.user_id.id})
        with self.assertRaises(AccessError):
            stronger.write({"login": "giang.do.2"})
        self.assertEqual(self.head.user_id.login, "giang.do")
        self.assertFalse(self.lab_head.user_id)

    def test_person_editor_cannot_grant_roles_or_permissions(self):
        own = self.as_person(self.head, self.head)
        administrator = self.env.ref("laboratory.role_administrator")

        for vals in (
            {"role_ids": [Command.link(administrator.id)]},
            {"permission_ids": [Command.link(self.permissions("person.edit.all").id)]},
        ):
            with self.subTest(vals=vals), self.assertRaises(AccessError):
                own.write(vals)

    def test_person_editor_does_not_see_users_roles_or_permissions(self):
        fields = self.as_person(self.env[MODEL_PERSON], self.head).fields_get()

        self.assertFalse({"user_id", "login", "role_ids", "permission_ids"} & set(fields))
