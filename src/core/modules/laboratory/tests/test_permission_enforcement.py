from lxml import etree

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.laboratory.constants.models import MODEL_DEPARTMENT


@tagged("post_install", "-at_install")
class TestPermissionEnforcement(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.chemistry = cls.env[MODEL_DEPARTMENT].create({"name": "Chemistry"})

    def user_with(self, *actions):
        groups = ["base.group_user"] + [f"laboratory.group_permission_department_{action}_all" for action in actions]
        return new_test_user(self.env, login=f"user.{'.'.join(actions) or 'none'}", groups=",".join(groups))

    def view_flags(self, user):
        views = self.env[MODEL_DEPARTMENT].with_user(user).get_views([(False, "list"), (False, "form")])["views"]
        return {
            view_type: {name: etree.fromstring(view["arch"]).get(name) for name in ("create", "edit", "delete")}
            for view_type, view in views.items()
        }

    def archive_offered(self, user):
        return not self.env[MODEL_DEPARTMENT].with_user(user).fields_get(["active"], ["readonly"])["active"]["readonly"]

    def test_user_without_permission_cannot_take_any_action(self):
        user = self.user_with()
        departments = self.env[MODEL_DEPARTMENT].with_user(user)
        chemistry = self.chemistry.with_user(user)

        for action in (
            lambda: departments.search([]),
            lambda: departments.create({"name": "Microbiology"}),
            lambda: chemistry.write({"name": "Analytical chemistry"}),
            chemistry.action_archive,
            chemistry.unlink,
        ):
            with self.subTest(action=action), self.assertRaises(AccessError):
                action()

    def test_reader_sees_no_create_edit_delete_or_archive(self):
        user = self.user_with("read")

        for view_type, flags in self.view_flags(user).items():
            with self.subTest(view=view_type):
                self.assertEqual(flags, {"create": "False", "edit": "False", "delete": "False"})
        self.assertFalse(self.archive_offered(user))

    def test_archive_without_edit_archives_but_cannot_change_fields(self):
        user = self.user_with("read", "archive")
        chemistry = self.chemistry.with_user(user)

        self.assertTrue(self.archive_offered(user))
        self.assertEqual(self.view_flags(user)["form"]["edit"], "False")
        with self.assertRaises(AccessError):
            chemistry.write({"name": "Analytical chemistry"})
        chemistry.action_archive()
        self.assertFalse(self.chemistry.active)

    def test_edit_without_archive_changes_fields_but_cannot_archive(self):
        user = self.user_with("read", "edit")
        chemistry = self.chemistry.with_user(user)

        self.assertFalse(self.archive_offered(user))
        self.assertIsNone(self.view_flags(user)["form"]["edit"])
        chemistry.write({"name": "Analytical chemistry"})
        self.assertEqual(self.chemistry.name, "Analytical chemistry")
        with self.assertRaises(AccessError):
            chemistry.action_archive()
        self.assertTrue(self.chemistry.active)

    def test_create_without_archive_creates_an_active_record(self):
        user = self.user_with("read", "create")

        department = self.env[MODEL_DEPARTMENT].with_user(user).create({"name": "Microbiology"})

        self.assertTrue(department.active)
        self.assertIsNone(self.view_flags(user)["form"]["create"])

    def test_delete_permission_deletes_an_unused_record(self):
        user = self.user_with("read", "delete")

        self.chemistry.with_user(user).unlink()

        self.assertFalse(self.chemistry.exists())

    def test_administrator_takes_every_action(self):
        user = new_test_user(self.env, login="lab.admin", groups="base.group_user,laboratory.group_role_administrator")
        departments = self.env[MODEL_DEPARTMENT].with_user(user)

        department = departments.create({"name": "Microbiology"})
        department.write({"name": "Microbiology lab"})
        department.action_archive()
        department.action_unarchive()
        department.unlink()
        self.assertTrue(self.archive_offered(user))
        self.assertEqual(self.view_flags(user)["form"], {"create": None, "edit": None, "delete": None})
