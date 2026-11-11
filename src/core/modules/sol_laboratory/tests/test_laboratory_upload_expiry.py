from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .laboratory_upload_case import LaboratoryUploadCase
from odoo.addons.sol_laboratory.constants.laboratory_bucket import PART_SIZE
from odoo.addons.sol_laboratory.constants.laboratory_files import FAILED, LOCKED, VERIFIED
from odoo.addons.sol_laboratory.constants.laboratory_uploads import (
    COMPLETED,
    EXPIRE_JOB,
    REFUSED,
    STORE_JOB,
    UPLOAD_CLOSED,
    UPLOAD_EXPIRED,
    VERIFY_JOB,
    VERIFYING,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_RES_CONFIG_SETTINGS, MODEL_SCHEDULED_JOB
from odoo.addons.sol_laboratory.constants.settings import DEFAULT_LABORATORY_UPLOAD_HOURS, LIFECYCLE_ABORT_HOURS
from odoo.addons.sol_laboratory.services import laboratory_bucket

RUN = b"mau,Pb\nLAB-26-0412,0.012\n"


@tagged("post_install", "-at_install")
class TestLaboratoryUploadExpiry(LaboratoryUploadCase):
    """Uploads that are never finalized, or never stored, expire, and their parts are removed; stored versions are
    untouched."""

    def expire_now(self, upload):
        # An upload keeps its expiry, so the test moves it with SQL.
        self.env.cr.execute(
            "UPDATE medilab_laboratory_upload SET expires_at = %s WHERE id = %s",
            [fields.Datetime.now() - timedelta(minutes=1), upload["id"]],
        )
        self.env.invalidate_all()

    def run_job(self, key):
        self.env[MODEL_SCHEDULED_JOB]._run_key(key)
        self.env.invalidate_all()

    def test_an_unfinished_upload_expires_and_its_parts_are_removed_while_stored_versions_are_untouched(self):
        stored = self.upload(RUN)
        stored_content = self.record(stored).content_id
        data = bytes(PART_SIZE + 10)
        upload = self.prepare(data, path="HPLC/large.raw").json()["upload"]
        self.put_parts(upload, data)
        record = self.record(upload)
        self.expire_now(upload)

        self.run_job(EXPIRE_JOB)

        self.assertEqual((record.status, record.content_id.state), (UPLOAD_EXPIRED, FAILED))
        with self.assertRaises(laboratory_bucket.UploadNotFound):
            laboratory_bucket.uploaded_parts(record.content_id.object_key, record.multipart_id)
        self.assertEqual(self.finalize(upload).json()["upload"]["status"], UPLOAD_EXPIRED)
        self.assertEqual(stored_content.state, VERIFIED)
        self.assertEqual(laboratory_bucket.object_size(stored_content.object_key), len(RUN))
        self.assertEqual(self.read_upload(stored)["status"], COMPLETED)

    def test_an_upload_past_its_expiry_is_not_finalized_even_before_the_job_marks_it(self):
        upload = self.prepare(RUN).json()["upload"]
        self.put_parts(upload, RUN)
        self.expire_now(upload)

        self.assertApiRefused(UPLOAD_CLOSED, self.finalize(upload))

    def test_a_refused_upload_expires_and_keeps_its_verified_content(self):
        file = self.file_of("HPLC/run-01.csv")
        self.save(file, "run 1")
        upload = self.prepare(RUN).json()["upload"]
        self.put_parts(upload, RUN)
        self.finalize(upload)
        self.run_job(VERIFY_JOB)
        file.with_user(self.member)._lock()
        self.run_job(STORE_JOB)
        record = self.record(upload)
        self.assertEqual((record.status, record.failure_code), (REFUSED, LOCKED))
        self.expire_now(upload)

        self.run_job(EXPIRE_JOB)

        self.assertEqual((record.status, record.content_id.state), (UPLOAD_EXPIRED, VERIFIED))
        self.assertEqual(laboratory_bucket.object_size(record.content_id.object_key), len(RUN))

    def test_an_upload_being_verified_does_not_expire(self):
        upload = self.prepare(RUN).json()["upload"]
        self.put_parts(upload, RUN)
        self.finalize(upload)
        self.expire_now(upload)

        self.run_job(EXPIRE_JOB)

        self.assertEqual(self.record(upload).status, VERIFYING)

    def test_an_upload_lasts_the_hours_of_the_settings_less_than_the_7_days_the_bucket_aborts_after(self):
        before = fields.Datetime.now()
        upload = self.prepare(RUN).json()["upload"]
        expected = before + timedelta(hours=DEFAULT_LABORATORY_UPLOAD_HOURS)

        self.assertAlmostEqual(self.record(upload).expires_at, expected, delta=timedelta(minutes=1))
        settings = self.env[MODEL_RES_CONFIG_SETTINGS]
        settings.create({"laboratory_upload_hours": LIFECYCLE_ABORT_HOURS - 1})
        for hours in (0, LIFECYCLE_ABORT_HOURS):
            with self.subTest(hours=hours), self.assertRaises(ValidationError):
                settings.create({"laboratory_upload_hours": hours})
