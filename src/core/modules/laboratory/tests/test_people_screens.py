from lxml import etree

from odoo.tests import tagged

from .people_case import PeopleCase
from odoo.addons.laboratory.constants.models import MODEL_DEPARTMENT, MODEL_PERMISSION, MODEL_PERSON, MODEL_ROLE

SCREENS = {
    "laboratory.menu_department": MODEL_DEPARTMENT,
    "laboratory.menu_person": MODEL_PERSON,
    "laboratory.menu_role": MODEL_ROLE,
    "laboratory.menu_permission": MODEL_PERMISSION,
}


@tagged("post_install", "-at_install")
class TestPeopleScreens(PeopleCase):
    def visible_menus(self, user):
        return {
            xml_id
            for xml_id in ("laboratory.menu_people_root", *SCREENS)
            if self.env.ref(xml_id).id in self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()
        }

    def test_person_without_permission_sees_no_people_menus(self):
        self.assertEqual(self.visible_menus(self.chemist.user_id), set())

    def test_reader_of_departments_sees_only_the_departments_menu(self):
        self.grant(self.chemist, "department.read.all")

        self.assertEqual(
            self.visible_menus(self.chemist.user_id), {"laboratory.menu_people_root", "laboratory.menu_department"}
        )

    def test_administrator_sees_every_people_menu(self):
        self.assertEqual(self.visible_menus(self.env.ref("base.user_admin")), {"laboratory.menu_people_root", *SCREENS})

    def test_readers_get_read_only_screens(self):
        self.grant(self.chemist, "department.read.all", "person.read.all", "role.read.all", "permission.read.all")
        for model in SCREENS.values():
            views = self.as_person(self.env[model], self.chemist).get_views([(False, "list"), (False, "form")])["views"]
            for view_type, view in views.items():
                root = etree.fromstring(view["arch"])
                with self.subTest(model=model, view=view_type):
                    self.assertEqual([root.get(name) for name in ("create", "edit", "delete")], ["False"] * 3)

    def test_person_form_hides_access_fields_from_people_editors(self):
        self.grant(self.chemist, "person.read.all", "person.edit.all")

        arch = self.as_person(self.env[MODEL_PERSON], self.chemist).get_views([(False, "form")])["views"]["form"][
            "arch"
        ]
        root = etree.fromstring(arch)

        for name in ("user_id", "login", "role_ids", "permission_ids", "action_open_user"):
            with self.subTest(name=name):
                self.assertFalse(root.xpath(f"//*[@name='{name}']"))

    def test_administrator_opens_the_users_form_from_the_person(self):
        action = self.chemist.action_open_user()

        self.assertEqual((action["res_model"], action["res_id"]), ("res.users", self.chemist.user_id.id))
