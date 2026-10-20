from odoo.exceptions import AccessError
from odoo.tests import tagged

from .laboratory_files_case import LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_UI_MENU,
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_FOLDER,
    MODEL_LABORATORY_FOLDER_MEMBER,
)

MENUS = ("folder", "folder_member", "sync_rule", "device")


@tagged("post_install", "-at_install")
class TestLaboratoryFilesBackOffice(LaboratoryFilesCase):
    def test_the_documents_menu_shows_to_people_with_the_laboratory_files_permission(self):
        menus = [self.env.ref(f"sol_laboratory.menu_laboratory_{name}").id for name in MENUS]
        documents = self.env.ref("sol_laboratory.menu_laboratory_documents").id

        for user in (self.tester, self.administrator):
            with self.subTest(user=user.login):
                visible = self.env[MODEL_IR_UI_MENU].with_user(user)._visible_menu_ids()
                self.assertFalse(set(menus) - set(visible))
        self.assertNotIn(documents, self.env[MODEL_IR_UI_MENU].with_user(self.colleague)._visible_menu_ids())

    def test_only_administrators_see_the_actions_on_folders_and_computers(self):
        for model, button in (
            (MODEL_LABORATORY_FOLDER, "action_archive_folder"),
            (MODEL_LABORATORY_DEVICE, "action_revoke"),
        ):
            arches = {
                user: self.env[model].with_user(user).get_views([(False, "form")])["views"]["form"]["arch"]
                for user in (self.administrator, self.tester)
            }
            with self.subTest(model=model):
                self.assertIn(button, arches[self.administrator])
                self.assertNotIn(button, arches[self.tester])

    def test_a_tester_reads_their_folders_and_changes_nothing_in_the_back_office(self):
        folder = self.folder.with_user(self.tester)

        self.assertEqual(folder.status, "in_use")
        with self.assertRaises(AccessError):
            folder.name = "HPLC 2026"
        with self.assertRaises(AccessError):
            self.env[MODEL_LABORATORY_FOLDER_MEMBER].with_user(self.tester).create(
                {"folder_id": self.folder.id, "user_id": self.outsider.id}
            )

    def test_a_folder_shows_whether_it_is_in_use_turned_off_or_archived(self):
        folder = self.folder.with_user(self.administrator)

        folder.action_turn_off()
        self.assertEqual(folder.status, "turned_off")
        folder.action_turn_on()
        folder.action_archive_folder()
        self.assertEqual(folder.status, "archived")
