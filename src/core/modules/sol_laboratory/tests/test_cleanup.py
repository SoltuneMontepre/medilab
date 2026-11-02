import datetime as _datetime_types
import gzip
import json
from datetime import timedelta
from hashlib import sha256
from unittest.mock import MagicMock, patch

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import SQL

from .audit_case import AuditLookup
from .people_case import PeopleCase
from odoo.addons.sol_laboratory.constants.jobs import (
    CLEANUP_CONTEXT,
    CLEANUP_JOB,
    CLEANUP_KINDS,
    CLEANUP_RETENTION_FIELDS,
    JOB_RUN_CONTEXT,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_ARCHIVE_FILE,
    MODEL_AUDIT_ENTRY,
    MODEL_DOCUMENT_LOCK,
    MODEL_JOB_ITEM,
    MODEL_JOB_RUN,
    MODEL_LABORATORY_FILE_LOCK,
    MODEL_MAIL_MESSAGE,
    MODEL_MAIL_NOTIFICATION,
    MODEL_MOBILE_DEVICE,
    MODEL_REGULATION,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.sol_laboratory.constants.settings import AUDIT_RETENTION_PARAMETER, DEFAULT_RETENTION_DAYS
from odoo.addons.sol_laboratory.tests.assertions import assert_instance

ARCHIVE_FILE_MODULE = "odoo.addons.sol_laboratory.models.system.archive_file"
OLD = DEFAULT_RETENTION_DAYS + 1
RECENT = DEFAULT_RETENTION_DAYS - 1


@tagged("post_install", "-at_install")
class TestCleanup(AuditLookup, PeopleCase):
    """Housekeeping records on both sides of the 90-day retention, and audit entries of a month long past."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.job = cls.env[MODEL_SCHEDULED_JOB]._by_key(CLEANUP_JOB)
        # The demo data sets its own periods and runs the job today; each test starts from the defaults.
        cls.env[MODEL_JOB_ITEM].search([("job_id", "=", cls.job.id)]).unlink()
        parameters = cls.env["ir.config_parameter"]
        settings = cls.env["res.config.settings"]
        for field in CLEANUP_RETENTION_FIELDS:
            parameters.set_int(
                assert_instance(getattr(settings._fields[field], "config_parameter"), str), DEFAULT_RETENTION_DAYS
            )
        parameters.set_int(AUDIT_RETENTION_PARAMETER, 0)
        cls.regulation = cls.env[MODEL_REGULATION].create({"code": "CLEANUP-TEST", "name": "Bottled water"})

    def ago(self, days):
        return fields.Datetime.now() - timedelta(days=days)

    def backdate(self, records, column, days):
        self.env.flush_all()
        self.env.cr.execute(
            SQL(
                "UPDATE %s SET %s = %s WHERE id IN %s",
                SQL.identifier(records._table),
                SQL.identifier(column),
                self.ago(days),
                tuple(records.ids),
            )
        )
        records.invalidate_recordset()

    def run_cleanup(self):
        # Two batches, as the cron would call again while items remain.
        self.job._run_batch()
        self.job._run_batch()
        self.env.invalidate_all()

    def archive_of(self, month):
        return self.env[MODEL_ARCHIVE_FILE].search([("period_start", "=", month)])

    @staticmethod
    def month_of(entries):
        return entries[0].create_date.date().replace(day=1)

    def job_items(self, status, days):
        items = self.env[MODEL_JOB_ITEM].create(
            {"job_id": self.job.id, "item_key": f"test:{status}:{days}", "status": status}
        )
        self.backdate(items, "write_date", days)
        return items

    def job_run(self, days):
        return self.env[MODEL_JOB_RUN].create(
            {"job_id": self.job.id, "started_at": self.ago(days), "ended_at": self.ago(days), "status": "succeeded"}
        )

    def lock(self, status, days):
        return self.env[MODEL_DOCUMENT_LOCK].create(
            {
                "document_model": MODEL_REGULATION,
                "document_id": self.regulation.id,
                "user_id": self.chemist.user_id.id,
                "status": status,
                "released_at": self.ago(days),
                "release_reason": "saved" if status == "released" else "expired",
            }
        )

    def notification(self, is_read, days):
        message = self.env[MODEL_MAIL_MESSAGE].create(
            {
                "model": MODEL_REGULATION,
                "res_id": self.regulation.id,
                "body": "Free to edit",
                "message_type": "notification",
                "notification_key": f"test:{is_read}:{days}",
                "date": self.ago(days),
            }
        )
        return self.env[MODEL_MAIL_NOTIFICATION].create(
            {
                "mail_message_id": message.id,
                "res_partner_id": self.chemist.user_id.partner_id.id,
                "notification_type": "inbox",
                "is_read": is_read,
            }
        )

    def device(self, active, days):
        device = self.env[MODEL_MOBILE_DEVICE].create(
            {
                "user_id": self.chemist.user_id.id,
                "token": f"token-{active}-{days}",
                "platform": "android",
                "active": active,
            }
        )
        self.backdate(device, "write_date", days)
        return device

    def old_audit_entries(self):
        self.env[MODEL_AUDIT_ENTRY]._log_event("integration", "Old call to PayOS", self.regulation)
        self.regulation.name = "Bottled mineral water"
        entries = self.entries(self.regulation)
        # Every entry of the regulation falls on the same day, 500 days back; the demo archive holds 400 days back.
        self.backdate(entries, "create_date", 500)
        return entries

    def test_records_older_than_their_retention_are_removed_and_newer_ones_stay(self):
        removed = [
            self.job_items("done", OLD),
            self.job_items("cancelled", OLD),
            self.job_run(OLD),
            self.lock("released", OLD),
            self.lock("expired", OLD),
            self.notification(True, OLD),
            self.device(False, OLD),
        ]
        kept = [
            self.job_items("done", RECENT),
            self.job_items("failed", OLD),
            self.job_run(RECENT),
            self.lock("released", RECENT),
            self.notification(True, RECENT),
            self.notification(False, OLD),
            self.device(False, RECENT),
            self.device(True, OLD),
        ]

        self.run_cleanup()

        for records in removed:
            self.assertFalse(records.with_context(active_test=False).exists(), records)
        for records in kept:
            self.assertTrue(records.with_context(active_test=False).exists(), records)

    def test_a_job_run_that_audit_entries_name_stays(self):
        run = self.job_run(OLD)
        self.env[MODEL_AUDIT_ENTRY].sudo().create(
            {"action": "job", "source": "job", "job_run_id": run.id, "note": "Ran"}
        )

        self.run_cleanup()

        self.assertTrue(run.exists())

    def test_audit_entries_are_kept_for_ever_until_a_retention_period_is_set(self):
        entries = self.old_audit_entries()

        self.run_cleanup()

        self.assertTrue(entries.exists())
        self.assertFalse(self.archive_of(self.month_of(entries)))

    def test_audit_entries_are_removed_once_their_checked_archive_file_is_written(self):
        entries = self.old_audit_entries()
        notes = set(entries.mapped("note"))
        month = self.month_of(entries)
        self.env["ir.config_parameter"].set_int(AUDIT_RETENTION_PARAMETER, 365)

        self.run_cleanup()

        archive = self.archive_of(month)
        self.assertFalse(entries.exists())
        self.assertEqual(len(archive), 1)
        data = bytes(archive.attachment_id.raw)
        self.assertEqual(archive.checksum, sha256(data).hexdigest())
        self.assertEqual((archive.row_count, archive.size_bytes), (len(entries), len(data)))
        rows = [json.loads(line) for line in gzip.decompress(data).decode().splitlines()]
        self.assertEqual({row["id"] for row in rows}, set(entries.ids))
        self.assertEqual({row["note"] for row in rows}, notes)
        self.assertTrue(
            any(change["new_value"] == "Bottled mineral water" for row in rows for change in row["changes"])
        )
        self.assertEqual(assert_instance(archive.period_start, _datetime_types.date).day, 1)
        self.assertEqual(archive.job_run_id.job_id, self.job)

    def test_audit_entries_stay_when_the_stored_file_does_not_match_its_checksum(self):
        entries = self.old_audit_entries()
        month = self.month_of(entries)
        written, stored = MagicMock(), MagicMock()
        written.hexdigest.return_value, stored.hexdigest.return_value = "written", "damaged"

        with (
            patch(f"{ARCHIVE_FILE_MODULE}.sha256", side_effect=[written, stored]),
            self.assertRaises(UserError),
            self.env.cr.savepoint(),
        ):
            archives = self.env[MODEL_ARCHIVE_FILE].with_context(**{JOB_RUN_CONTEXT: self.job_run(1).id})
            archives._archive_audit_month(month)

        self.assertTrue(entries.exists())

    def test_nobody_removes_audit_entries_but_the_cleanup_job(self):
        entries = self.old_audit_entries()
        administrator = self.env.ref("base.user_admin")

        with self.assertRaises((AccessError, UserError)):
            entries.with_user(administrator).with_context(**{CLEANUP_CONTEXT: True}).unlink()
        with self.assertRaises(UserError):
            entries.unlink()

    def test_the_job_never_removes_business_records_or_signatures(self):
        housekeeping = {model for model, _retention in CLEANUP_KINDS.values()}

        self.assertEqual(
            housekeeping,
            {
                MODEL_JOB_ITEM,
                MODEL_JOB_RUN,
                MODEL_DOCUMENT_LOCK,
                MODEL_MAIL_NOTIFICATION,
                MODEL_MOBILE_DEVICE,
                MODEL_LABORATORY_FILE_LOCK,
            },
        )
        self.backdate(self.regulation, "write_date", 1000)
        self.run_cleanup()
        self.assertTrue(self.regulation.exists())

    def test_an_administrator_downloads_an_archive_file_and_others_cannot(self):
        entries = self.old_audit_entries()
        month = self.month_of(entries)
        self.env["ir.config_parameter"].set_int(AUDIT_RETENTION_PARAMETER, 365)
        self.run_cleanup()
        archive = self.archive_of(month)
        self.grant(self.chemist, "archive_file.read.all")

        action = archive.with_user(self.chemist.user_id).action_download()

        self.assertEqual(action["url"], f"/web/content/{archive.attachment_id.id}?download=true")
        self.assertTrue(archive.attachment_id.with_user(self.chemist.user_id).read(["raw"])[0]["raw"])
        with self.assertRaises(AccessError):
            archive.attachment_id.with_user(self.microbiologist.user_id).read(["raw"])

    def test_retention_periods_cannot_remove_records_still_within_them(self):
        settings = self.env["res.config.settings"]

        with self.assertRaises(ValidationError):
            settings.create({"audit_retention_days": -30})
        with self.assertRaises(ValidationError):
            settings.create({"job_retention_days": 0})
