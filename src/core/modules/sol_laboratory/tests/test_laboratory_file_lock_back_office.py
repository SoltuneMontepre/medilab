from odoo.exceptions import AccessError
from odoo.tests import tagged

from .laboratory_file_locks_case import LaboratoryFileLocksCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_UI_MENU,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_LOCK,
)

RELEASE_GROUP = "sol_laboratory.group_permission_laboratory_folder_edit_all"


@tagged("post_install", "-at_install")
class TestLaboratoryFileLockBackOffice(LaboratoryFileLocksCase):
    def test_file_locks_show_under_documents_to_people_with_the_laboratory_files_permission(self):
        menu = self.env.ref("sol_laboratory.menu_laboratory_file_lock").id

        for user in (self.tester, self.administrator):
            with self.subTest(user=user.login):
                self.assertIn(menu, self.env[MODEL_IR_UI_MENU].with_user(user)._visible_menu_ids())
        self.assertNotIn(menu, self.env[MODEL_IR_UI_MENU].with_user(self.colleague)._visible_menu_ids())

    def test_members_read_the_locks_of_their_folders_and_change_none(self):
        lock = self.lock_as(self.tester)
        locks = self.env[MODEL_LABORATORY_FILE_LOCK]

        for user in (self.tester, self.member):
            with self.subTest(user=user.login):
                self.assertEqual(locks.with_user(user).search([]), lock)
        self.assertIn(lock, locks.with_user(self.administrator).search([]))
        for user in (self.tester, self.member, self.administrator):
            with self.subTest(user=user.login):
                with self.assertRaises(AccessError):
                    lock.with_user(user).write({"status": "released"})
        self.assertFalse(locks.with_user(self.outsider).search([]))
        with self.assertRaises(AccessError):
            locks.with_user(self.colleague).search([])

    def test_a_file_shows_who_holds_its_lock_until_when(self):
        lock = self.lock_as(self.tester)
        file = self.file.with_user(self.member)

        self.assertEqual((file.locked_by_id, file.locked_until), (self.tester, lock.expires_at))
        self.assertEqual(file.lock_ids, lock)
        arch = self.env[MODEL_LABORATORY_FILE].with_user(self.member).get_views([(False, "form")])["views"]["form"]
        self.assertIn('name="lock_ids"', arch["arch"])
        self.assertIn('name="locked_until"', arch["arch"])

    def test_only_folder_administrators_see_the_release_button(self):
        for user, shown in ((self.member, False), (self.administrator, True)):
            for view in ("list", "form"):
                with self.subTest(user=user.login, view=view):
                    arch = self.env[MODEL_LABORATORY_FILE_LOCK].with_user(user).get_views([(False, view)])
                    self.assertEqual('name="action_release"' in arch["views"][view]["arch"], shown)
        self.assertTrue(self.administrator.has_group(RELEASE_GROUP))
