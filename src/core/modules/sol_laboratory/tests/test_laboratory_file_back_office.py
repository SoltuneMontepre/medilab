from odoo.exceptions import AccessError
from odoo.tests import tagged

from .laboratory_files_case import LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_UI_MENU,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_LABORATORY_FOLDER,
)
from odoo.addons.sol_laboratory.services.model_lookup import reference_as


@tagged("post_install", "-at_install")
class TestLaboratoryFileBackOffice(LaboratoryFilesCase):
    def test_files_and_versions_show_under_documents_to_people_with_the_laboratory_files_permission(self):
        menus = {
            reference_as(self.env[MODEL_IR_UI_MENU], f"sol_laboratory.menu_laboratory_{name}").id
            for name in ("file", "file_version")
        }

        for user in (self.tester, self.administrator):
            with self.subTest(user=user.login):
                self.assertFalse(menus - set(self.env[MODEL_IR_UI_MENU].with_user(user)._visible_menu_ids()))
        self.assertFalse(menus & set(self.env[MODEL_IR_UI_MENU].with_user(self.colleague)._visible_menu_ids()))

    def test_the_back_office_reads_files_and_versions_and_changes_nothing(self):
        file = self.file_of("HPLC/run-01.csv")
        version = self.save(file, "run 1")

        for user in (self.member, self.administrator):
            for model in (MODEL_LABORATORY_FILE, MODEL_LABORATORY_FILE_VERSION):
                with self.subTest(user=user.login, model=model):
                    views = self.env[model].with_user(user).get_views([(False, "list"), (False, "form")])
                    self.assertEqual(set(views["views"]), {"list", "form"})
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                self.env[MODEL_LABORATORY_FILE].with_user(user).create({"folder_id": self.folder.id, "path": "x.csv"})
        self.assertEqual(file.with_user(self.member).current_number, version.number)

    def test_a_folder_lists_its_files(self):
        file = self.file_of("HPLC/run-01.csv")
        self.save(file, "run 1")
        arch = self.env[MODEL_LABORATORY_FOLDER].with_user(self.member).get_views([(False, "form")])["views"]["form"]

        self.assertIn('name="file_ids"', arch["arch"])
        self.assertEqual(self.folder.with_user(self.member).file_ids, file)
