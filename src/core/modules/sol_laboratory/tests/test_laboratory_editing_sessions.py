from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .laboratory_editing_case import LaboratoryEditingCase
from .laboratory_sample_folder_case import LaboratorySampleFolderCase
from odoo.addons.sol_laboratory.constants.laboratory_editing import (
    CLOSED,
    EXPIRED,
    NOT_EDITABLE,
    OPEN,
    REPORT,
    SAVING,
)
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    FOLDER_ARCHIVED,
    FOLDER_DISABLED,
    NOT_FOUND,
    PERMISSION_DENIED,
    RAW_DATA,
    RESULT,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_EDITING_SESSION
from odoo.addons.sol_laboratory.constants.settings import LABORATORY_EDITING_IDLE_PARAMETER


@tagged("post_install", "-at_install")
class TestLaboratoryEditingSessions(LaboratoryEditingCase, LaboratorySampleFolderCase):
    def open(self, user, file=None):
        return self.env[MODEL_LABORATORY_EDITING_SESSION].with_user(user)._open_for((file or self.file).with_user(user))

    def idle_since(self, session, hours):
        session.sudo().last_activity_at = fields.Datetime.now() - timedelta(hours=hours)
        session.flush_recordset()

    def test_opening_an_office_file_opens_a_session_on_its_current_version(self):
        session = self.open(self.tester)

        self.assertEqual(
            (session.status, session.file_id, session.base_version_id, session.opened_by_id),
            (OPEN, self.file, self.first, self.tester),
        )
        self.assertEqual(self.entries(session).mapped("action"), ["create"])

    def test_a_second_person_opening_the_file_joins_the_same_session(self):
        session = self.open(self.tester)

        joined = self.open(self.member)

        self.assertEqual(joined, session)
        self.assertEqual(joined._callback_token(), session._callback_token())
        self.assertEqual(len(self.file.editing_session_ids), 1)
        self.assertIn(self.member.name, (self.entries(session, "edit").note or ""))

    def test_a_person_joins_the_session_even_when_the_file_has_a_newer_version(self):
        session = self.open(self.tester)
        self.save(self.file, "Kết quả, bản 2 từ máy tính", user=self.member)

        joined = self.open(self.member)

        self.assertEqual((joined, joined.base_version_id), (session, self.first))

    def test_a_session_still_saving_is_joined(self):
        session = self.open(self.tester)
        session.sudo().status = SAVING

        self.assertEqual(self.open(self.member), session)

    def test_a_session_idle_for_12_hours_expires_and_the_next_person_opens_a_new_one(self):
        session = self.open(self.tester)
        second = self.save(self.file, "Kết quả, bản 2", user=self.member)
        self.idle_since(session, 13)

        opened = self.open(self.member)

        self.assertEqual(session.status, EXPIRED)
        self.assertNotEqual(opened, session)
        self.assertEqual((opened.status, opened.base_version_id, opened.opened_by_id), (OPEN, second, self.member))
        self.assertNotEqual(opened.document_key, session.document_key)

    def test_a_session_within_the_idle_period_is_joined(self):
        session = self.open(self.tester)
        self.idle_since(session, 11)

        self.assertEqual(self.open(self.member), session)

    def test_the_idle_period_is_a_setting(self):
        self.env["ir.config_parameter"].sudo().set_int(LABORATORY_EDITING_IDLE_PARAMETER, 1)
        session = self.open(self.tester)
        self.idle_since(session, 2)

        self.assertNotEqual(self.open(self.member), session)
        self.assertEqual(session.status, EXPIRED)

    def test_opening_a_file_whose_session_ended_starts_a_new_one(self):
        session = self.open(self.tester)
        session.sudo().status = CLOSED

        self.assertNotEqual(self.open(self.tester), session)

    def spreadsheet_in(self, category):
        """A saved results spreadsheet of a new folder of the category, as a folder keeps its category once it holds
        files."""
        folder = self.folder_of_category(category, name=f"HPLC {category or 'none'}")
        file = self.file_of("Kết quả.xlsx", folder)
        self.save(file, "Kết quả, bản 1")
        return file

    def test_office_files_of_result_and_working_folders_and_of_folders_without_a_category_are_edited_online(self):
        for category in (RESULT, "working", False):
            with self.subTest(category=category):
                file = self.spreadsheet_in(category)
                self.assertEqual(self.open(self.tester, file).file_id, file)

    def test_raw_data_and_report_files_are_never_edited_online(self):
        for category in (RAW_DATA, REPORT):
            with self.subTest(category=category):
                file = self.spreadsheet_in(category)
                self.assertRefused(NOT_EDITABLE, self.open, self.tester, file)
                self.assertFalse(file.editing_session_ids)

    def test_only_word_excel_and_powerpoint_files_are_edited_online(self):
        for path, editable in (
            ("2026/Báo cáo.DOCX", True),
            ("2026/Trình bày.pptx", True),
            ("2026/run-01.csv", False),
            ("2026/Kết quả.xls", False),
            ("2026/Báo cáo.pdf", False),
        ):
            with self.subTest(path=path):
                file = self.file_of(path)
                self.save(file, path)
                if editable:
                    self.assertEqual(self.open(self.tester, file).file_id, file)
                else:
                    self.assertRefused(NOT_EDITABLE, self.open, self.tester, file)

    def test_a_file_without_a_version_is_not_opened(self):
        self.assertRefused(NOT_EDITABLE, self.open, self.tester, self.file_of("2026/Mới.xlsx"))

    def test_only_members_with_the_laboratory_files_permission_open_a_file_of_a_folder_taking_uploads(self):
        self.assertRefused(NOT_FOUND, self.open, self.outsider)
        self.assertRefused(PERMISSION_DENIED, self.open, self.colleague)
        self.folder.with_user(self.administrator).action_turn_off()
        self.assertRefused(FOLDER_DISABLED, self.open, self.member)
        self.folder.with_user(self.administrator).action_archive_folder()
        self.assertRefused(FOLDER_ARCHIVED, self.open, self.member)
        self.assertFalse(self.file.editing_session_ids)
