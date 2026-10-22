import hashlib
import hmac

from psycopg2 import IntegrityError

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger
from odoo.tools.misc import hmac as database_hmac

from .laboratory_editing_case import LaboratoryEditingCase
from odoo.addons.sol_laboratory.constants.laboratory_editing import (
    CALLBACK_TOKEN_SCOPE,
    CLOSED,
    COMMITTED,
    EXPIRED,
    OPEN,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_CONFIG_PARAMETER,
    MODEL_LABORATORY_EDITING_SESSION,
    MODEL_LABORATORY_FILE,
)


@tagged("post_install", "-at_install")
class TestLaboratoryEditingSessionRecords(LaboratoryEditingCase):
    def test_only_the_hash_of_the_callback_token_is_stored_and_it_finds_the_session(self):
        session = self.new_session()
        sessions = self.env[MODEL_LABORATORY_EDITING_SESSION]

        token = session._callback_token()

        self.assertNotIn(token, (session.callback_token, session.document_key))
        self.assertEqual(sessions._from_callback_token(token), session)
        for wrong in ("", f"{token}x", session.callback_token, session.document_key):
            with self.subTest(token=wrong):
                self.assertFalse(sessions._from_callback_token(wrong))

    def test_the_callback_token_is_signed_under_a_scope_of_its_own(self):
        session = self.new_session()
        secret = self.env[MODEL_IR_CONFIG_PARAMETER].sudo().get_str("database.secret")

        token = session._callback_token()

        self.assertEqual(token, database_hmac(self.env(su=True), CALLBACK_TOKEN_SCOPE, session.document_key))
        self.assertNotEqual(token, hmac.new(secret.encode(), session.document_key.encode(), hashlib.sha256).hexdigest())
        self.assertNotEqual(token, database_hmac(self.env(su=True), "sol_laboratory.other", session.document_key))

    def test_everyone_in_a_session_gets_its_token_and_each_session_has_its_own(self):
        session = self.new_session()
        session.status = CLOSED
        session.flush_recordset()
        other = self.new_session()

        self.assertEqual(session._callback_token(), session.with_user(self.member)._callback_token())
        self.assertNotEqual(session._callback_token(), other._callback_token())
        self.assertNotEqual(session.document_key, other.document_key)

    def test_a_file_has_one_open_session_at_a_time(self):
        session = self.new_session()

        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.new_session(user=self.member)
        session.status = CLOSED
        session.flush_recordset()
        self.assertEqual(self.new_session(user=self.member).status, OPEN)

    def test_a_session_keeps_its_file_its_version_its_keys_and_its_opener(self):
        session = self.new_session()
        other = self.file_of("2026/Bản nháp.docx")
        self.save(other, "bản nháp")

        for vals in (
            {"file_id": other.id},
            {"base_version_id": other.current_version_id.id},
            {"document_key": "another-key"},
            {"callback_token": "another-hash"},
            {"opened_by_id": self.member.id},
        ):
            with self.subTest(vals=vals), self.assertRaises(UserError):
                session.write(vals)

    def test_an_ended_session_is_not_opened_again(self):
        committed = self.new_session()
        committed.write({"status": COMMITTED, "committed_version_id": self.save(self.file, "bản 2").id})

        with self.assertRaises(UserError):
            committed.status = OPEN
        with self.assertRaises(UserError):
            committed.status = EXPIRED

    def test_an_expired_session_still_saves(self):
        session = self.new_session()
        session.status = EXPIRED

        session.write({"status": COMMITTED, "committed_version_id": self.save(self.file, "bản 2").id})

        self.assertEqual(session.status, COMMITTED)

    def test_a_session_saves_one_version(self):
        session = self.new_session()
        session.committed_version_id = self.save(self.file, "bản 2")

        with self.assertRaises(UserError):
            session.committed_version_id = self.save(self.file, "bản 3")

    def test_a_session_opens_and_saves_versions_of_its_own_file(self):
        other = self.file_of("2026/Bản nháp.docx")
        other_version = self.save(other, "bản nháp")
        session = self.new_session()

        with self.assertRaises(ValidationError):
            session.committed_version_id = other_version
        sessions = self.env[MODEL_LABORATORY_EDITING_SESSION].sudo()
        document_key, token_hash = sessions._new_keys()
        with self.assertRaises(ValidationError):
            sessions.create(
                {
                    "file_id": other.id,
                    "base_version_id": self.first.id,
                    "document_key": document_key,
                    "callback_token": token_hash,
                    "opened_by_id": self.tester.id,
                }
            )

    def test_sessions_are_never_deleted(self):
        session = self.new_session()

        with self.assertRaises(UserError):
            session.unlink()

    def test_members_read_the_sessions_of_their_folders_and_change_none(self):
        session = self.new_session()
        sessions = self.env[MODEL_LABORATORY_EDITING_SESSION]

        self.assertEqual(sessions.with_user(self.member).search([]), session)
        self.assertFalse(sessions.with_user(self.outsider).search([]))
        self.assertFalse(sessions.with_user(self.colleague).has_access("read"))
        with self.assertRaises(AccessError):
            session.with_user(self.member).write({"status": CLOSED})

    def test_administrators_read_every_session(self):
        session = self.new_session()

        self.assertIn(session, self.env[MODEL_LABORATORY_EDITING_SESSION].with_user(self.administrator).search([]))

    def test_the_trail_records_a_session_under_its_file_and_masks_its_token(self):
        session = self.new_session()
        session.write({"status": CLOSED, "last_activity_at": "2026-10-21 08:00:00"})

        created, edited = self.entries(session)
        changes = {change.field_name: change.new_value for change in created.change_ids}
        self.assertEqual((created.parent_model, created.parent_id), (MODEL_LABORATORY_FILE, self.file.id))
        self.assertEqual(changes["callback_token"], "***")
        self.assertNotIn("last_activity_at", changes)
        self.assertEqual(edited.change_ids.mapped("field_name"), ["status"])
