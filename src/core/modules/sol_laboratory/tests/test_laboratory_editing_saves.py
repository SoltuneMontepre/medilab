from unittest.mock import patch

from odoo.tests import tagged

from .laboratory_editing_case import LaboratoryEditingCase
from odoo.addons.sol_laboratory.constants.laboratory_editing import (
    CLOSED,
    COMMITTED,
    ERROR,
    EXPIRED,
    OPEN,
    SAVING,
    SESSION_CONFLICT,
)
from odoo.addons.sol_laboratory.constants.laboratory_files import CONFLICT, EDITED_ONLINE, LOCKED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_CHANGE,
    MODEL_LABORATORY_FOLDER_MEMBER,
)
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError


@tagged("post_install", "-at_install")
class TestLaboratoryEditingSaves(LaboratoryEditingCase):
    def setUp(self):
        super().setUp()
        self.session = self.new_session()

    def store(self, content, session=None, editor=None, editors=None):
        """The save of the editing service once its content is stored, as the callback makes it."""
        editor = editor or self.tester
        return (session or self.session)._store_save(
            content=self.stored(content), editor=editor, editors=editors or editor
        )

    def test_saving_in_the_editor_adds_a_version_marked_edited_online_that_becomes_current(self):
        version = self.store("Kết quả, sửa trực tuyến")

        self.assertEqual(
            (version.source, version.number, version.parent_version_id, version.user_id, version.device_id),
            (EDITED_ONLINE, 2, self.first, self.tester, self.env[MODEL_LABORATORY_DEVICE]),
        )
        self.assertEqual(self.file.current_version_id, version)
        self.assertEqual((self.session.status, self.session.committed_version_id), (COMMITTED, version))
        changes = self.env[MODEL_LABORATORY_FILE_CHANGE].search([("file_id", "=", self.file.id)])
        self.assertEqual(changes[-1:].version_id, version)

    def test_the_version_goes_to_the_last_editor_and_the_trail_names_every_editor(self):
        version = self.store("Kết quả, sửa chung", editor=self.member, editors=self.tester | self.member)

        self.assertEqual(version.user_id, self.member)
        note = self.entries(self.session, "edit")[-1].note
        self.assertIn(self.member.name, (note or ""))
        self.assertIn(self.tester.name, (note or ""))

    def test_a_save_after_the_file_changed_is_kept_as_a_conflict(self):
        synced = self.save(self.file, "Kết quả, bản 2 từ máy tính", user=self.member)

        version = self.store("Kết quả, sửa trực tuyến")

        self.assertEqual((version.source, version.parent_version_id), (CONFLICT, synced))
        self.assertEqual(self.file.current_version_id, synced)
        self.assertEqual((self.session.status, self.session.committed_version_id), (SESSION_CONFLICT, version))

    def test_a_save_with_the_content_the_file_has_adds_nothing_and_closes_the_session(self):
        version = self.store("Kết quả, bản 1")

        self.assertEqual(version, self.first)
        self.assertEqual(len(self.file.version_ids), 1)
        self.assertEqual(self.session.status, CLOSED)
        self.assertFalse(self.session.committed_version_id)

    def test_a_repeated_save_stores_nothing_twice(self):
        version = self.store("Kết quả, sửa trực tuyến")
        entries = self.entries(self.session)

        self.assertEqual(self.store("Kết quả, sửa trực tuyến"), version)
        self.assertEqual(self.store("Kết quả, sửa lại"), version)
        self.assertEqual(len(self.file.version_ids), 2)
        self.assertEqual(self.entries(self.session), entries)

    def test_a_save_repeated_after_a_conflict_a_close_or_an_error_stores_nothing(self):
        session = self.session
        for status in (SESSION_CONFLICT, CLOSED, ERROR):
            with self.subTest(status=status):
                session.sudo().status = status
                session.flush_recordset()
                self.assertFalse(self.store(f"Kết quả, {status}", session=session))
                session = self.new_session()
        self.assertEqual(len(self.file.version_ids), 1)

    def test_a_save_arriving_after_the_session_expired_is_stored(self):
        self.session.sudo().status = EXPIRED
        self.session.flush_recordset()
        later = self.new_session(user=self.member)

        version = self.store("Kết quả, sửa 13 giờ")

        self.assertEqual((version.source, self.file.current_version_id), (EDITED_ONLINE, version))
        self.assertEqual((self.session.status, self.session.committed_version_id), (COMMITTED, version))
        self.assertEqual(later.status, OPEN)

    def test_a_save_arriving_after_the_session_expired_and_the_file_changed_is_a_conflict(self):
        self.session.sudo().status = EXPIRED
        synced = self.save(self.file, "Kết quả, bản 2 từ máy tính", user=self.member)

        version = self.store("Kết quả, sửa 13 giờ")

        self.assertEqual((version.source, self.file.current_version_id), (CONFLICT, synced))
        self.assertEqual(self.session.status, SESSION_CONFLICT)

    def test_an_editor_who_can_no_longer_write_the_file_ends_the_session_in_error_and_the_trail_keeps_the_content(
        self,
    ):
        self.env[MODEL_LABORATORY_FOLDER_MEMBER].search(
            [("folder_id", "=", self.folder.id), ("user_id", "=", self.member.id)]
        ).unlink()

        self.assertFalse(self.store("Kết quả, sửa trực tuyến", editor=self.member))

        self.assertEqual(len(self.file.version_ids), 1)
        self.assertEqual(self.session.status, ERROR)
        note = self.entries(self.session, "edit")[-1].note
        self.assertIn(self.stored("Kết quả, sửa trực tuyến").object_key, (note or ""))
        self.assertIn(self.member.name, (note or ""))

    def test_a_save_into_a_turned_off_folder_ends_the_session_in_error(self):
        self.folder.with_user(self.administrator).action_turn_off()

        self.assertFalse(self.store("Kết quả, sửa trực tuyến"))

        self.assertEqual((self.session.status, len(self.file.version_ids)), (ERROR, 1))

    def test_a_rule_every_save_obeys_refuses_the_save_and_ends_the_session_in_error(self):
        # As a rule a feature built on files adds would, through their extension point.
        def refuse(files, user, device):
            raise LaboratoryFileError(LOCKED, "Locked by someone else.")

        with patch.object(type(self.env[MODEL_LABORATORY_FILE]), "_check_can_add_version", refuse):
            self.assertFalse(self.store("Kết quả, sửa trực tuyến"))

        self.assertEqual((self.session.status, len(self.file.version_ids)), (ERROR, 1))
        self.assertIn("Locked by someone else.", (self.entries(self.session, "edit")[-1].note or ""))

    def test_everyone_leaving_without_changes_closes_the_session(self):
        self.session._close_unchanged()

        self.assertEqual((self.session.status, len(self.file.version_ids)), (CLOSED, 1))

    def test_a_save_that_fails_for_a_while_keeps_the_session_saving_until_it_is_stored(self):
        self.session._keep_saving()
        self.assertEqual(self.session.status, SAVING)

        version = self.store("Kết quả, sửa trực tuyến")

        self.assertEqual((self.session.status, self.session.committed_version_id), (COMMITTED, version))

    def test_an_expired_session_whose_save_fails_for_a_while_stays_expired(self):
        self.session.sudo().status = EXPIRED

        self.session._keep_saving()

        self.assertEqual(self.session.status, EXPIRED)

    def test_a_failed_save_ends_the_session_in_error_with_why(self):
        self.session._fail("The saved document could not be read.")

        self.assertEqual(self.session.status, ERROR)
        self.assertEqual(self.entries(self.session, "edit")[-1].note, "The saved document could not be read.")

    def test_a_failure_or_a_close_after_the_save_changes_nothing(self):
        version = self.store("Kết quả, sửa trực tuyến")

        self.session._fail("The editing service could not save the document.")
        self.session._close_unchanged()
        self.session._keep_saving()

        self.assertEqual((self.session.status, self.session.committed_version_id), (COMMITTED, version))
