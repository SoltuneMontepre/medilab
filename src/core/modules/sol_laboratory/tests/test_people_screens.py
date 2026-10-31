from ast import literal_eval

from lxml import etree

from odoo.tests import tagged

from .people_case import PeopleCase
from odoo.addons.sol_laboratory.constants.models import MODEL_DEPARTMENT, MODEL_PERMISSION, MODEL_PERSON, MODEL_ROLE
from odoo.addons.sol_laboratory.constants.xml_ids import DEPARTMENTS_MENU
from odoo.addons.sol_laboratory.services.model_lookup import dynamic_model, reference_as
from odoo.addons.sol_laboratory.tests.assertions import assert_instance

SCREENS = {
    "sol_laboratory.menu_person": MODEL_PERSON,
    "sol_laboratory.menu_role": MODEL_ROLE,
    "sol_laboratory.menu_permission": MODEL_PERMISSION,
}


@tagged("post_install", "-at_install")
class TestPeopleScreens(PeopleCase):
    def visible_menus(self, user):
        shown = self.env["ir.ui.menu"].with_user(user).load_menus(False)
        return {xml_id for xml_id in (DEPARTMENTS_MENU, *SCREENS) if self.env.ref(xml_id).id in shown}

    def listed_departments(self, user):
        domain = literal_eval(assert_instance(self.env.ref("hr.hr_department_kanban_action").domain, str))
        return self.env[MODEL_DEPARTMENT].with_user(user).search(domain)

    def test_people_menus_are_in_odoos_employees_app(self):
        for xml_id in SCREENS:
            with self.subTest(menu=xml_id):
                self.assertEqual(
                    reference_as(self.env["ir.ui.menu"], xml_id).parent_id, self.env.ref("hr.menu_hr_root")
                )

    def test_person_without_permission_sees_no_people_menus(self):
        self.assertEqual(self.visible_menus(self.chemist.user_id), set())
        self.assertFalse(self.listed_departments(self.chemist.user_id))

    def test_reader_of_departments_sees_every_department_in_odoos_departments_menu(self):
        self.grant(self.chemist, "department.read.all")

        self.assertEqual(self.visible_menus(self.chemist.user_id), {DEPARTMENTS_MENU})
        self.assertTrue(self.chemistry | self.microbiology <= self.listed_departments(self.chemist.user_id))

    def test_administrator_sees_every_people_menu(self):
        self.assertEqual(self.visible_menus(self.env.ref("base.user_admin")), {DEPARTMENTS_MENU, *SCREENS})

    def test_readers_get_read_only_screens(self):
        self.grant(self.chemist, "department.read.all", "person.read.all", "role.read.all", "permission.read.all")
        for model in (MODEL_DEPARTMENT, *SCREENS.values()):
            views = self.as_person(dynamic_model(self.env, model), self.chemist).get_views(
                [(False, "list"), (False, "form")]
            )["views"]
            for view_type, view in views.items():
                root = etree.fromstring(view["arch"])
                with self.subTest(model=model, view=view_type):
                    self.assertEqual([root.get(name) for name in ("create", "edit", "delete")], ["False"] * 3)

    def test_person_screens_hide_access_fields_from_people_editors(self):
        self.grant(self.chemist, "person.read.all", "person.edit.all")

        views = self.as_person(self.env[MODEL_PERSON], self.chemist).get_views([(False, "list"), (False, "form")])
        for view_type, view in views["views"].items():
            root = etree.fromstring(view["arch"])
            for name in ("user_id", "work_contact_id", "login", "role_ids", "permission_ids", "action_open_user"):
                with self.subTest(view=view_type, name=name):
                    self.assertFalse(root.xpath(f"//*[@name='{name}']"))

    def test_administrator_opens_the_users_form_from_the_person(self):
        action = self.chemist.action_open_user()

        self.assertEqual((action["res_model"], action["res_id"]), ("res.users", self.chemist.user_id.id))
