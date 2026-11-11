import hashlib
from unittest.mock import patch

from odoo.tests import tagged

from .editing_service import PUBLIC_URL, LocalEditingService, callback, use_editing_service
from .laboratory_editing_concurrency_case import LaboratoryEditingConcurrencyCase
from .laboratory_files_case import stored_content
from odoo.addons.sol_laboratory.constants.laboratory_editing import COMMITTED, OPEN, SESSION_CONFLICT
from odoo.addons.sol_laboratory.constants.laboratory_files import CONFLICT, EDITED_ONLINE, SYNCED
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_EDITING_SESSION,
)


def sha(content):
    return hashlib.sha256(content.encode()).hexdigest()


@tagged("post_install", "-at_install")
class TestLaboratoryEditingConcurrency(LaboratoryEditingConcurrencyCase):
    """Two real database transactions opening, saving and expiring an editing session at once, the second one through
    Odoo's request retrying."""

    def test_two_people_opening_a_file_at_once_make_one_session(self):
        first_id = []
        attempts, second_id = self.race(lambda env: first_id.append(self.open(env).id), self.open)

        self.assertEqual(attempts, 2)
        self.assertEqual(second_id, first_id[0])
        self.assertEqual(self.state()[1], [(OPEN, False)])

    def test_two_calls_of_one_save_at_once_store_one_version(self):
        self.committed(self.open)

        attempts, version_id = self.race(
            lambda env: self.store(env, "bản sửa trực tuyến"), lambda env: self.store(env, "bản sửa trực tuyến")
        )

        self.assertEqual(attempts, 2)
        self.assertEqual(self.state(), ([(1, SYNCED), (2, EDITED_ONLINE)], [(COMMITTED, 2)]))
        self.assertEqual(self.committed(lambda env: self.session(env).committed_version_id.id), version_id)

    def test_an_upload_and_an_online_save_at_once_get_the_next_two_numbers_and_the_save_is_a_conflict(self):
        self.committed(self.open)

        attempts, _version_id = self.race(
            lambda env: self.upload(self.file(env), "bản 2 từ máy tính"),
            lambda env: self.store(env, "bản sửa trực tuyến"),
        )

        self.assertEqual(attempts, 2)
        self.assertEqual(self.state(), ([(1, SYNCED), (2, SYNCED), (3, CONFLICT)], [(SESSION_CONFLICT, 3)]))

    def test_a_save_arriving_while_its_session_expires_is_stored(self):
        self.committed(self.go_idle)

        attempts, _version_id = self.race(self.expire, lambda env: self.store(env, "bản sửa 13 giờ"))

        self.assertEqual(attempts, 2)
        self.assertEqual(self.state(), ([(1, SYNCED), (2, EDITED_ONLINE)], [(COMMITTED, 2)]))

    def test_expiring_a_session_its_save_just_ended_changes_nothing(self):
        self.committed(self.go_idle)

        attempts, _session_id = self.race(lambda env: self.store(env, "bản sửa 13 giờ"), self.expire)

        self.assertEqual(attempts, 2)
        self.assertEqual(self.state(), ([(1, SYNCED), (2, EDITED_ONLINE)], [(COMMITTED, 2)]))

    def serve_saved_document(self, content):
        """The editing service giving the saved document, and its content recorded as verified without the bucket."""
        service = LocalEditingService(self)
        service.answer("/cache/output.xlsx", content.encode())
        use_editing_service(self, internal_url=service.url)

        def store(session, chunks):
            return stored_content(session.env, b"".join(chunks).decode())

        bucket = patch.object(
            type(self.env[MODEL_LABORATORY_EDITING_SESSION]), "_store_saved_document", autospec=True, side_effect=store
        )
        bucket.start()
        self.addCleanup(bucket.stop)

    def call_back(self, env, status):
        session = self.session(env)
        admin = str(env.ref("base.user_admin").id)
        body, header = callback(
            {"key": session.document_key, "status": status, "url": f"{PUBLIC_URL}/cache/output.xlsx", "users": [admin]}
        )
        found, fields = env[MODEL_LABORATORY_EDITING_SESSION]._from_callback(session._callback_token(), body, header)
        found._receive_callback(fields)
        return found

    def entries(self):
        def work(env):
            env.cr.execute(
                "SELECT action FROM medilab_audit_entry WHERE id > %s AND document_model = %s ORDER BY id",
                [self.last_entry_id, MODEL_LABORATORY_EDITING_SESSION],
            )
            return [action for (action,) in env.cr.fetchall()]

        return self.committed(work)

    def test_two_calls_of_one_save_callback_at_once_store_one_version_and_one_entry(self):
        self.serve_saved_document("bản sửa trực tuyến")
        self.committed(self.open)

        attempts, _session_id = self.race(lambda env: self.call_back(env, 2), lambda env: self.call_back(env, 2))

        self.assertEqual(attempts, 2)
        self.assertEqual(self.state(), ([(1, SYNCED), (2, EDITED_ONLINE)], [(COMMITTED, 2)]))
        self.assertEqual(self.entries(), ["create", "edit"])

    def test_someone_editing_while_the_save_is_stored_loses_nothing(self):
        self.serve_saved_document("bản sửa trực tuyến")
        self.committed(self.open)

        attempts, _session_id = self.race(lambda env: self.call_back(env, 2), lambda env: self.call_back(env, 1))

        self.assertEqual(attempts, 2)
        self.assertEqual(self.state(), ([(1, SYNCED), (2, EDITED_ONLINE)], [(COMMITTED, 2)]))

    def test_a_save_callback_arriving_while_its_session_expires_is_stored(self):
        self.serve_saved_document("bản sửa 13 giờ")
        self.committed(self.go_idle)

        attempts, _session_id = self.race(self.expire, lambda env: self.call_back(env, 2))

        self.assertEqual(attempts, 2)
        self.assertEqual(self.state(), ([(1, SYNCED), (2, EDITED_ONLINE)], [(COMMITTED, 2)]))

    def test_an_upload_and_a_save_callback_at_once_keep_the_save_as_a_conflict(self):
        self.serve_saved_document("bản sửa trực tuyến")
        self.committed(self.open)

        attempts, _session_id = self.race(
            lambda env: self.upload(self.file(env), "bản 2 từ máy tính"), lambda env: self.call_back(env, 2)
        )

        self.assertEqual(attempts, 2)
        self.assertEqual(self.state(), ([(1, SYNCED), (2, SYNCED), (3, CONFLICT)], [(SESSION_CONFLICT, 3)]))
