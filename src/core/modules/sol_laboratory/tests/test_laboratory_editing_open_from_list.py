from lxml import etree

from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import tagged

from .laboratory_editing_case import LaboratoryEditingCase
from .laboratory_sample_folder_case import LaboratorySampleFolderCase
from odoo.addons.sol_laboratory.constants.laboratory_editing import REPORT
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    MEMBER_ROLE,
    RAW_DATA,
    RESULT,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FILE, MODEL_LABORATORY_FOLDER


@tagged("post_install", "-at_install")
class TestLaboratoryEditingOpenFromList(LaboratoryEditingCase, LaboratorySampleFolderCase):
    def editor_action(self, file):
        return {"type": "ir.actions.act_url", "url": f"/medilab/laboratory-files/{file.id}/edit", "target": "new"}

    def form_action(self, file):
        return {
            "type": "ir.actions.act_window",
            "res_model": MODEL_LABORATORY_FILE,
            "res_id": file.id,
            "view_mode": "form",
            "views": [(False, "form")],
        }

    def file_in(self, category, path="Kết quả.xlsx"):
        """A saved file of a new folder of the category."""
        folder = self.folder_of_category(category, name=f"HPLC {category or 'none'}")
        file = self.file_of(path, folder)
        self.save(file, "Kết quả, bản 1")
        return file

    def test_a_click_on_an_office_file_the_user_writes_opens_its_editor_page_in_a_new_tab(self):
        for user in (self.tester, self.member):
            with self.subTest(user=user.login):
                self.assertEqual(self.file.with_user(user).action_open(), self.editor_action(self.file))

    def test_opening_a_file_creates_no_editing_session(self):
        self.file.with_user(self.member).action_open()

        self.assertFalse(self.file.editing_session_ids)

    def test_office_files_of_result_and_working_folders_open_online(self):
        for category in (RESULT, "working", False):
            with self.subTest(category=category):
                file = self.file_in(category)
                self.assertEqual(file.with_user(self.tester).action_open(), self.editor_action(file))

    def test_raw_data_report_and_non_office_files_open_their_form(self):
        for file in (
            self.file_in(RAW_DATA),
            self.file_in(REPORT),
            self.file_of("2026/run-01.csv"),
            self.file_of("2026/Kết quả.xls"),
        ):
            with self.subTest(path=file.path, folder=file.folder_id.name):
                if not file.current_version_id:
                    self.save(file, file.path)
                self.assertEqual(file.with_user(self.tester).action_open(), self.form_action(file))

    def test_a_file_without_a_version_opens_its_form(self):
        file = self.file_of("2026/Mới.xlsx")

        self.assertEqual(file.with_user(self.tester).action_open(), self.form_action(file))

    def test_a_member_who_may_read_but_not_write_the_file_opens_its_form(self):
        for change in ("action_turn_off", "action_archive_folder"):
            with self.subTest(change=change):
                folder = self.folder_of_category(False, name=f"HPLC {change}")
                folder.member_ids = [Command.create({"user_id": self.member.id, "role": MEMBER_ROLE})]
                file = self.file_of("Kết quả.xlsx", folder)
                self.save(file, "Kết quả, bản 1")
                getattr(folder.with_user(self.administrator), change)()

                self.assertEqual(file.with_user(self.member).action_open(), self.form_action(file))

    def test_nobody_without_read_access_is_given_an_action(self):
        for user in (self.outsider, self.colleague):
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                self.file.with_user(user).action_open()

    def test_an_administrator_who_is_not_a_member_opens_the_form_of_a_file_they_read(self):
        self.assertEqual(self.file.with_user(self.administrator).action_open(), self.form_action(self.file))

    def test_a_click_acts_on_one_file(self):
        other = self.file_of("2026/Kết quả HPLC tháng 11.xlsx")

        with self.assertRaises(ValueError):
            (self.file | other).with_user(self.tester).action_open()

    def test_the_files_list_opens_files_with_action_open_and_the_folder_files_tab_keeps_its_form(self):
        views = self.env[MODEL_LABORATORY_FILE].with_user(self.member).get_views([(False, "list")])["views"]
        arch = etree.fromstring(views["list"]["arch"])
        folder_views = self.env[MODEL_LABORATORY_FOLDER].with_user(self.member).get_views([(False, "form")])["views"]
        folder_files = etree.fromstring(folder_views["form"]["arch"]).find(".//field[@name='file_ids']/list")

        self.assertEqual((arch.get("action"), arch.get("type")), ("action_open", "object"))
        if folder_files is None:
            self.fail("The folder form lists no files.")
        self.assertIsNone(folder_files.get("action"))
