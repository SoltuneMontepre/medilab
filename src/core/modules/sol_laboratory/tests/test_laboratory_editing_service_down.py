import os
from unittest.mock import patch

from odoo.tests import tagged

from .laboratory_editing_case import LaboratoryEditingCase
from odoo.addons.sol_laboratory.constants.laboratory_editing import INTERNAL_URL_VARIABLE, OPEN, SESSION_CONFLICT
from odoo.addons.sol_laboratory.constants.laboratory_files import RESTORED, SYNCED
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FILE_VERSION


@tagged("post_install", "-at_install")
class TestLaboratoryEditingServiceDown(LaboratoryEditingCase):
    """Without the editing service, and with a session open on the file, everything else about files keeps working."""

    def setUp(self):
        super().setUp()
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop(INTERNAL_URL_VARIABLE, None)
        self.session = self.new_session()

    def test_syncing_a_file_open_online_adds_its_current_version(self):
        synced = self.save(self.file, "Kết quả, bản 2 từ máy tính", user=self.member)

        self.assertEqual((synced.source, self.file.current_version_id), (SYNCED, synced))
        self.assertEqual(self.session.status, OPEN)

    def test_restoring_a_file_open_online_adds_its_current_version(self):
        self.save(self.file, "Kết quả, bản 2 từ máy tính")

        restored = self.file._add_version(
            source=RESTORED,
            user=self.member,
            restored_from=self.first,
        )

        self.assertEqual((restored.source, self.file.current_version_id), (RESTORED, restored))

    def test_members_read_the_history_of_a_file_open_online(self):
        second = self.save(self.file, "Kết quả, bản 2 từ máy tính")

        versions = (
            self.env[MODEL_LABORATORY_FILE_VERSION].with_user(self.member).search([("file_id", "=", self.file.id)])
        )

        self.assertEqual(versions, second | self.first)

    def test_the_session_saves_a_conflict_once_the_file_was_synced_meanwhile(self):
        synced = self.save(self.file, "Kết quả, bản 2 từ máy tính")

        version = self.session._store_save(
            content=self.stored("sửa trực tuyến"), editor=self.tester, editors=self.tester
        )

        self.assertEqual((self.session.status, self.file.current_version_id), (SESSION_CONFLICT, synced))
        self.assertEqual(version.parent_version_id, synced)

    def test_syncing_restoring_and_reading_history_never_ask_the_editing_service(self):
        self.save(self.file, "Kết quả, bản 2 từ máy tính", user=self.member)
        self.file._add_version(
            source=RESTORED,
            user=self.member,
            restored_from=self.first,
        )
        self.env[MODEL_LABORATORY_FILE_VERSION].with_user(self.member).search([("file_id", "=", self.file.id)])

        self.health_check.assert_not_called()
