from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .audit_case import AuditLookup
from .laboratory_files_case import LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    RETENTION_METADATA_CONTEXT,
    RETENTION_REMOVED,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_CONTENT,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FOLDER,
    MODEL_SCHEDULED_JOB,
)


@tagged("post_install", "-at_install")
class TestLaboratoryFolderRetention(AuditLookup, LaboratoryFilesCase):
    def setUp(self):
        super().setUp()
        self.file = self.file_of("HPLC/run-01.csv")

    def expire(self, folder):
        folder.with_user(self.administrator).write(
            {
                "archived_at": fields.Datetime.now(),
                "retention_until": fields.Date.context_today(folder) - timedelta(days=1),
            }
        )
        self.env.invalidate_all()

    def flag_due_folders(self):
        self.env[MODEL_SCHEDULED_JOB]._run_key("laboratory_folder.retention_review")
        self.env.invalidate_all()

    def test_a_context_flag_cannot_change_an_archived_folder_without_superuser_rights(self):
        self.expire(self.folder)

        with self.assertRaises(UserError):
            self.folder.with_user(self.administrator).with_context(**{RETENTION_METADATA_CONTEXT: True}).write(
                {"retention_review_required": True}
            )

    def test_the_daily_job_flags_expired_folders_without_removing_any_content(self):
        version = self.save(self.file, "retained bytes")
        self.expire(self.folder)

        self.flag_due_folders()

        self.assertTrue(self.folder.retention_review_required)
        self.assertEqual(version.content_id.state, "verified")
        self.assertFalse(self.folder.retention_approved_at)

    def test_an_administrator_cannot_approve_before_the_daily_job_flags_the_folder(self):
        version = self.save(self.file, "not yet reviewed")
        self.expire(self.folder)

        with self.assertRaises(UserError):
            self.folder.with_user(self.administrator).action_approve_retention_removal()

        self.assertEqual(version.content_id.state, "verified")
        self.assertFalse(self.folder.retention_approved_at)

    def test_only_an_administrator_can_approve_and_history_and_signed_content_stay(self):
        signed = self.save(self.file, "signed bytes")
        removable = self.save(self.file, "unsigned bytes")
        signed.sudo().write({"approval_state": "approved"})
        self.expire(self.folder)
        self.flag_due_folders()

        with self.assertRaises(UserError):
            self.folder.with_user(self.tester).action_approve_retention_removal()
        self.folder.with_user(self.administrator).action_approve_retention_removal()

        self.assertEqual(signed.content_id.state, "verified")
        self.assertFalse(removable.content_id)
        self.assertTrue(removable.content_removed_at)
        self.assertEqual(removable.sha256, self.sha("unsigned bytes"))
        self.assertEqual(len(self.file.version_ids), 2)
        self.assertTrue(self.folder.retention_approved_at)
        self.assertEqual(self.folder.retention_approved_by_id, self.administrator)
        self.assertEqual(self.file.current_version_id, removable)
        folder_audit = self.entries(self.folder, "edit")[-1]
        version_audit = self.entries(removable, "edit")[-1]
        self.assertEqual(folder_audit.user_id, self.administrator)
        self.assertEqual(version_audit.user_id, self.administrator)
        self.assertEqual(set(self.changes(version_audit)), {"content_id", "content_removed_at"})
        with self.assertRaises(UserError):
            removable._read_address(60)

    def test_content_shared_with_another_folder_stays_until_both_are_approved(self):
        other_folder = self.env[MODEL_LABORATORY_FOLDER].create({"name": "AAS", "owner_id": self.tester.id})
        version = self.save(self.file, "shared bytes")
        other_file = self.env[MODEL_LABORATORY_FILE]._get_or_create(other_folder, "run-01.csv")
        other_version = self.save(other_file, "shared bytes")
        self.expire(self.folder)
        self.expire(other_folder)
        self.flag_due_folders()

        self.folder.with_user(self.administrator).action_approve_retention_removal()

        self.assertFalse(version.content_id)
        self.assertEqual(other_version.content_id.state, "verified")
        other_folder.with_user(self.administrator).action_approve_retention_removal()
        self.assertFalse(other_version.content_id)
        content = (
            self.env[MODEL_LABORATORY_CONTENT]
            .sudo()
            .search([("sha256", "=", self.sha("shared bytes")), ("state", "=", RETENTION_REMOVED)], limit=1)
        )
        self.assertTrue(content)
