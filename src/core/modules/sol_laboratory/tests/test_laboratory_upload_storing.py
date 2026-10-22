from odoo.tests import tagged

from .audit_case import AuditLookup
from .laboratory_upload_case import LaboratoryUploadCase
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    DEVICE_REVOKED,
    FOLDER_ARCHIVED,
    FOLDER_DISABLED,
    LOCKED,
    NOT_FOUND,
    VERIFIED,
)
from odoo.addons.sol_laboratory.constants.laboratory_uploads import (
    COMPLETED,
    REFUSED,
    STORE_JOB,
    VERIFY_JOB,
    VERIFYING,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FOLDER_MEMBER,
    MODEL_SCHEDULED_JOB,
)

RUN = b"mau,Pb\nLAB-26-0412,0.012\n"


@tagged("post_install", "-at_install")
class TestLaboratoryUploadStoring(AuditLookup, LaboratoryUploadCase):
    """Storing the version of an upload once its content is verified, as the person who uploaded it, and what refuses
    it meanwhile."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.auditor = cls.new_auditor()

    def verified(self, data=RUN, path="HPLC/run-01.csv", key=None):
        """An upload finalized and verified, whose version is not stored yet."""
        upload = self.prepare(data, path, key=key).json()["upload"]
        self.put_parts(upload, data, key=key)
        self.finalize(upload, key=key)
        self.env[MODEL_SCHEDULED_JOB]._run_key(VERIFY_JOB)
        self.env.invalidate_all()
        self.assertEqual(self.record(upload).status, VERIFYING)
        return upload

    def store(self):
        self.env[MODEL_SCHEDULED_JOB]._run_key(STORE_JOB)
        self.env.invalidate_all()

    def assertRefusedWith(self, code, refuse):
        """An upload from the member's computer whose storing the change refuses ends refused with the code, and keeps
        its verified content."""
        member_key = self.signed_in_key(self.member, "member-installation")
        upload = self.verified(key=member_key)
        refuse()

        self.store()

        record = self.record(upload)
        self.assertEqual((record.status, record.failure_code, record.version_id.id), (REFUSED, code, False))
        self.assertEqual(record.content_id.state, VERIFIED)

    def test_a_lock_someone_else_took_meanwhile_refuses_storing(self):
        def lock():
            file = self.file_of("HPLC/run-01.csv")
            self.save(file, "run, saved before")
            file.with_user(self.tester)._lock()

        self.assertRefusedWith(LOCKED, lock)

    def test_a_computer_revoked_meanwhile_refuses_storing(self):
        devices = self.env[MODEL_LABORATORY_DEVICE]
        self.assertRefusedWith(
            DEVICE_REVOKED, lambda: devices.search([("client_uid", "=", "member-installation")]).action_revoke()
        )

    def test_a_folder_turned_off_meanwhile_refuses_storing(self):
        folder = self.folder.with_user(self.administrator)
        self.assertRefusedWith(FOLDER_DISABLED, folder.action_turn_off)

    def test_a_folder_archived_meanwhile_refuses_storing(self):
        folder = self.folder.with_user(self.administrator)
        self.assertRefusedWith(FOLDER_ARCHIVED, folder.action_archive_folder)

    def test_a_person_removed_from_the_folder_meanwhile_refuses_storing(self):
        members = self.env[MODEL_LABORATORY_FOLDER_MEMBER]
        self.assertRefusedWith(
            NOT_FOUND,
            lambda: members.search([("folder_id", "=", self.folder.id), ("user_id", "=", self.member.id)]).unlink(),
        )

    def test_a_refused_upload_is_finalized_again_once_the_lock_is_gone_and_stores_its_version(self):
        file = self.file_of("HPLC/run-01.csv")
        self.save(file, "run 1")
        upload = self.verified()
        file.with_user(self.member)._lock()
        self.store()
        self.assertEqual(self.read(upload)["status"], REFUSED)

        file.with_user(self.member)._unlock()
        finalized = self.finalize(upload)
        self.store()

        self.assertEqual(finalized.json()["upload"]["status"], VERIFYING)
        read = self.read(upload)
        self.assertEqual((read["status"], read["failure_code"], read["version"]["number"]), (COMPLETED, None, 2))

    def test_the_file_of_a_new_path_is_made_once_the_version_is_stored(self):
        upload = self.verified(path="HPLC/new.csv")
        self.assertFalse(self.record(upload).file_id)

        self.store()

        file = self.env[MODEL_LABORATORY_FILE].search(
            [("folder_id", "=", self.folder.id), ("path", "=", "HPLC/new.csv")]
        )
        self.assertEqual(self.record(upload).file_id, file)
        self.assertEqual(file.current_version_id, self.record(upload).version_id)

    def test_an_upload_is_audited_under_its_file_from_preparing_to_storing(self):
        file = self.file_of("HPLC/run-01.csv")
        self.save(file, "run 1")
        upload = self.verified()
        self.store()

        record = self.record(upload)
        entries = self.entries(record).sorted("id")
        self.assertEqual(entries.mapped("action"), ["create", "edit", "edit"])
        self.assertEqual({(entry.parent_model, entry.parent_id) for entry in entries}, {(file._name, file.id)})
        self.assertEqual(
            [self.changes(entry).get("status") for entry in entries[1:]],
            [("prepared", VERIFYING), (VERIFYING, COMPLETED)],
        )
        self.assertEqual(entries[0].user_id, self.tester)
        self.assertTrue(self.entries(record.version_id))
