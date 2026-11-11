import hashlib
import os
from datetime import datetime, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged

from .editing_service import PUBLIC_URL, LocalEditingService, callback, use_editing_service
from .laboratory_bucket_case import closed_port, remove_written_objects
from .laboratory_editing_case import LaboratoryEditingCase
from odoo.addons.sol_laboratory.constants.laboratory_bucket import ADDRESS_VARIABLE
from odoo.addons.sol_laboratory.constants.laboratory_editing import (
    CLOSED,
    COMMITTED,
    ERROR,
    EXPIRED,
    JWT_SECRET_VARIABLE,
    OPEN,
    SAVING,
    SESSION_CONFLICT,
)
from odoo.addons.sol_laboratory.constants.laboratory_files import DUPLICATE, EDITED_ONLINE, SYNCED, VERIFIED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_CONTENT,
    MODEL_LABORATORY_EDITING_SESSION,
    MODEL_LABORATORY_FOLDER_MEMBER,
)
from odoo.addons.sol_laboratory.services import laboratory_bucket, saved_documents
from odoo.addons.sol_laboratory.services.onlyoffice_jwt import EditingCallbackRefused
from odoo.addons.sol_laboratory.tests.assertions import assert_instance

SAVED_PATH = "/cache/files/data/session_902/output.xlsx/output.xlsx"
CONTENT = "Kết quả HPLC, sửa trực tuyến".encode()
SAVED_SHA256 = hashlib.sha256(CONTENT).hexdigest()


@tagged("post_install", "-at_install")
class TestLaboratoryEditingCallbacks(LaboratoryEditingCase):
    """The editing service's callbacks, checked and acted on as the callback route does."""

    def setUp(self):
        super().setUp()
        self.service = LocalEditingService(self)
        use_editing_service(self, internal_url=self.service.url)
        self.service.answer(SAVED_PATH, CONTENT)
        self.session = self.new_session()
        self.sessions = self.env[MODEL_LABORATORY_EDITING_SESSION]
        remove_written_objects(self)

    def saved_key(self):
        """The key of the object that holds the saved document."""
        contents = self.env[MODEL_LABORATORY_CONTENT].sudo()
        return contents.search([("state", "=", VERIFIED), ("sha256", "=", SAVED_SHA256)]).object_key

    def call(self, status, session=None, token=None, **values):
        """Send the session a callback of the status, as Document Server 9.4 sends it, and return whether it is answered
        with success."""
        session = session or self.session
        body, header = callback({"key": session.document_key, "status": status, **values})
        found, checked = self.sessions._from_callback(token or session._callback_token(), body, header)
        return found._receive_callback(checked)

    def save_online(self, editor=None, **values):
        editor = editor or self.member
        values.setdefault("url", f"{PUBLIC_URL}{SAVED_PATH}?md5=abc&expires=1&filename=output.xlsx")
        values.setdefault("history", {"changes": [{"user": {"id": str(self.tester.id), "name": self.tester.name}}]})
        return self.call(2, users=[str(editor.id)], **values)

    def assertNothingStored(self, status=OPEN):
        self.assertEqual((self.session.status, len(self.file.version_ids)), (status, 1))
        # Only the session's opening, and its move to saving.
        self.assertEqual(len(self.entries(self.session)), 1 if status == OPEN else 2)

    def test_saving_in_the_editor_adds_a_version_marked_edited_online_for_the_last_editor(self):
        self.assertTrue(self.save_online())

        version = self.file.current_version_id
        self.assertEqual((version.source, version.user_id, version.sha256), (EDITED_ONLINE, self.member, SAVED_SHA256))
        self.assertEqual((self.session.status, self.session.committed_version_id), (COMMITTED, version))
        note = self.entries(self.session, "edit")[-1].note
        self.assertIn(self.member.name, (note or ""))
        self.assertIn(self.tester.name, (note or ""))

    def test_the_saved_document_is_fetched_from_the_internal_address_with_its_path_and_query(self):
        self.save_online()

        self.assertEqual(self.service.asked, [f"{SAVED_PATH}?md5=abc&expires=1&filename=output.xlsx"])

    def test_a_save_after_the_file_changed_is_a_conflict(self):
        synced = self.save(self.file, "Kết quả, bản 2 từ máy tính")

        self.assertTrue(self.save_online())

        self.assertEqual((self.session.status, self.file.current_version_id), (SESSION_CONFLICT, synced))

    def test_a_repeated_save_stores_one_version_and_one_entry_and_fetches_nothing_again(self):
        self.save_online()
        entries = len(self.entries(self.session))

        self.assertTrue(self.save_online())

        self.assertEqual(len(self.file.version_ids), 2)
        self.assertEqual(len(self.entries(self.session)), entries)
        self.assertEqual(len(self.service.asked), 1)

    def test_a_save_for_an_expired_session_is_stored(self):
        self.session.sudo().status = EXPIRED

        self.assertTrue(self.save_online())

        self.assertEqual(self.session.status, COMMITTED)

    def test_an_editor_who_lost_access_ends_the_session_in_error_and_the_trail_keeps_the_content(self):
        self.env[MODEL_LABORATORY_FOLDER_MEMBER].search(
            [("folder_id", "=", self.folder.id), ("user_id", "=", self.member.id)]
        ).unlink()

        self.assertTrue(self.save_online())

        self.assertEqual((self.session.status, len(self.file.version_ids)), (ERROR, 1))
        self.assertIn(self.saved_key(), (self.entries(self.session, "edit")[-1].note or ""))

    def test_a_save_naming_nobody_who_can_save_ends_the_session_in_error_and_the_trail_keeps_the_content(self):
        for number, users in enumerate(([], ["999999"], ["7a"], [7])):
            with self.subTest(users=users):
                file = self.file_of(f"2026/Kết quả {number}.xlsx")
                self.save(file, "Kết quả, bản 1")
                session = self.new_session(file=file)

                self.assertTrue(self.call(2, session=session, url=f"{PUBLIC_URL}{SAVED_PATH}", users=users))

                self.assertEqual(session.status, ERROR)
                self.assertIn(self.saved_key(), (self.entries(session, "edit")[-1].note or ""))

    def test_a_save_that_cannot_be_read_now_keeps_the_session_saving_and_asks_for_the_call_again(self):
        self.service.answer(SAVED_PATH, status=500)

        self.assertFalse(self.save_online())
        self.assertNothingStored(SAVING)

        self.service.answer(SAVED_PATH, CONTENT)
        self.assertTrue(self.save_online())
        self.assertEqual(self.session.status, COMMITTED)

    def test_the_saved_document_is_written_to_an_object_of_its_own_and_verified_on_the_way(self):
        self.assertTrue(self.save_online())

        content = self.file.current_version_id.content_id.sudo()
        self.assertEqual((content.state, content.sha256, content.size), (VERIFIED, SAVED_SHA256, len(CONTENT)))
        with laboratory_bucket.read(content.object_key) as chunks:
            self.assertEqual(b"".join(chunks), CONTENT)

    def test_a_save_of_content_already_stored_shares_it_and_its_own_object_is_deleted_once_committed(self):
        contents = self.env[MODEL_LABORATORY_CONTENT].sudo()
        stored = contents._new_pending()
        laboratory_bucket.write(stored.object_key, iter([CONTENT]))
        stored._settle(SAVED_SHA256, len(CONTENT))
        self.file_of("2026/Bản sao.xlsx")._add_version(content=stored, source=SYNCED, user=self.tester)

        self.assertTrue(self.save_online())

        self.assertEqual(self.file.current_version_id.content_id, stored)
        duplicate = contents.search([("sha256", "=", SAVED_SHA256), ("state", "=", DUPLICATE)])
        self.assertEqual(laboratory_bucket.object_size(duplicate.object_key), len(CONTENT))
        self.env.cr.postcommit.run()
        self.assertIsNone(laboratory_bucket.object_size(duplicate.object_key))
        self.assertEqual(laboratory_bucket.object_size(stored.object_key), len(CONTENT))

    def test_a_save_whose_transaction_fails_after_its_object_is_written_leaves_nothing_that_counts(self):
        written = []
        write = laboratory_bucket.write

        def recording(key, chunks):
            written.append(key)
            self.addCleanup(laboratory_bucket.delete, key)
            return write(key, chunks)

        def fail(*args, **kwargs):
            raise RuntimeError("The transaction of the callback fails.")

        with (
            patch.object(laboratory_bucket, "write", recording),
            patch.object(type(self.sessions), "_store_save", fail),
            self.assertRaises(RuntimeError),
            self.env.cr.savepoint(),
        ):
            self.save_online()

        [key] = written
        self.assertEqual(laboratory_bucket.object_size(key), len(CONTENT))
        self.assertFalse(self.env[MODEL_LABORATORY_CONTENT].sudo().search([("object_key", "=", key)]))
        self.assertNothingStored()

    def test_without_the_laboratory_files_bucket_a_save_waits(self):
        with patch.dict(os.environ, {ADDRESS_VARIABLE: f"http://127.0.0.1:{closed_port()}"}):
            self.assertFalse(self.save_online())

        self.assertNothingStored(SAVING)

    def test_a_document_over_the_limit_ends_the_session_in_error(self):
        with patch.object(saved_documents, "MAX_SIZE", len(CONTENT) - 1):
            self.assertTrue(self.save_online())

        self.assertEqual((self.session.status, len(self.file.version_ids)), (ERROR, 1))

    def test_a_save_on_any_other_origin_is_refused_and_fetches_nothing(self):
        for url in (f"https://attacker.example{SAVED_PATH}", f"http://169.254.169.254{SAVED_PATH}", None):
            with self.subTest(url=url), self.assertRaises(EditingCallbackRefused):
                self.call(2, url=url, users=[str(self.member.id)])

        self.assertNothingStored()
        self.assertEqual(self.service.asked, [])

    def test_someone_editing_is_activity_and_writes_no_entry(self):
        for status in (1, 6, 7):
            with self.subTest(status=status):
                self.session.sudo().last_activity_at = fields.Datetime.now() - timedelta(hours=1)

                self.assertTrue(self.call(status, url=f"{PUBLIC_URL}{SAVED_PATH}", users=[str(self.member.id)]))

                self.assertGreater(
                    assert_instance(self.session.last_activity_at, datetime),
                    fields.Datetime.now() - timedelta(minutes=1),
                )
                self.assertNothingStored()
        self.assertEqual(self.service.asked, [])

    def test_everyone_leaving_without_changes_closes_the_session(self):
        self.assertTrue(self.call(4))

        self.assertEqual((self.session.status, len(self.file.version_ids)), (CLOSED, 1))

    def test_a_save_the_editing_service_could_not_make_ends_the_session_in_error(self):
        self.assertTrue(self.call(3, url=f"{PUBLIC_URL}{SAVED_PATH}"))

        self.assertEqual((self.session.status, len(self.file.version_ids)), (ERROR, 1))
        self.assertEqual(self.service.asked, [])

    def test_a_status_the_editing_service_never_sends_is_refused(self):
        for status in (0, 5, 8, True, "2", None):
            with self.subTest(status=status), self.assertRaises(EditingCallbackRefused):
                self.call(status)

        self.assertNothingStored()

    def test_a_callback_failing_a_check_stores_nothing(self):
        other_file = self.file_of("2026/Kết quả khác.xlsx")
        self.save(other_file, "Kết quả khác, bản 1")
        other = self.new_session(file=other_file)
        body, header = callback({"key": self.session.document_key, "status": 2, "url": f"{PUBLIC_URL}{SAVED_PATH}"})
        other_body, other_header = callback({"key": other.document_key, "status": 4})
        forged_body, forged_header = callback({"key": self.session.document_key, "status": 4}, secret="x" * 40)
        for token, body, header in (
            ("not-a-token", body, header),
            (other._callback_token(), body, header),
            (self.session._callback_token(), other_body, other_header),
            (self.session._callback_token(), forged_body, forged_header),
            (self.session._callback_token(), {"key": self.session.document_key, "status": 4}, None),
        ):
            with self.subTest(token=token[:12]), self.assertRaises(EditingCallbackRefused):
                self.sessions._from_callback(token, body, header)

        self.assertNothingStored()
        self.assertEqual(self.service.asked, [])

    def test_without_the_secret_every_callback_is_refused(self):
        body, header = callback({"key": self.session.document_key, "status": 4})
        os.environ.pop(JWT_SECRET_VARIABLE)

        with self.assertRaises(EditingCallbackRefused):
            self.sessions._from_callback(self.session._callback_token(), body, header)
