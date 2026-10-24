import hashlib
import os
import uuid
from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import fields
from odoo.tests import tagged

from .laboratory_upload_case import LaboratoryUploadCase
from odoo.addons.sol_laboratory.constants.laboratory_bucket import NAME_VARIABLE
from odoo.addons.sol_laboratory.constants.laboratory_reconciliation import MARKER_KEY, RECONCILE_JOB
from odoo.addons.sol_laboratory.constants.laboratory_uploads import REFUSED, UPLOAD_EXPIRED, VERIFYING
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_ENTRY,
    MODEL_IR_CONFIG_PARAMETER,
    MODEL_LABORATORY_CONTENT,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.sol_laboratory.services import laboratory_bucket

# The bucket of local development and CI that only these tests use, as reconciliation deletes what this database has no
# content of, and the test shards share one server.
RECONCILE_BUCKET = "laboratory-files-reconcile"


@tagged("post_install", "-at_install")
class TestLaboratoryContentReconcile(LaboratoryUploadCase):
    """The daily job that compares the laboratory files bucket with the stored content: it deletes what no content
    needs once a day old, aborts the multipart uploads of no open upload, and records the rest as errors."""

    def setUp(self):
        super().setUp()
        patcher = patch.dict(os.environ, {NAME_VARIABLE: RECONCILE_BUCKET})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.empty_bucket()
        self.addCleanup(self.empty_bucket)
        self.contents = self.env[MODEL_LABORATORY_CONTENT].sudo()

    def empty_bucket(self):
        for key, _size, _modified in list(laboratory_bucket.objects()):
            laboratory_bucket.delete(key)
        for key, upload_id, _initiated in list(laboratory_bucket.multipart_uploads()):
            laboratory_bucket.abort_upload(key, upload_id)

    def reconcile(self, days_later=2):
        """Run the job as its cron does, the given number of days after now."""
        with freeze_time(fields.Datetime.now() + timedelta(days=days_later)):
            self.env[MODEL_SCHEDULED_JOB]._run_key(RECONCILE_JOB)
        self.env.invalidate_all()

    def exists(self, key):
        return laboratory_bucket.object_size(key) is not None

    def errors(self, text):
        return self.env[MODEL_AUDIT_ENTRY].sudo().search([("action", "=", "error"), ("note", "ilike", text)])

    def unique_bytes(self):
        # Bytes no demo file and no other test has, so settling them never finds content already stored.
        return f"Kết quả {uuid.uuid4()}".encode()

    def stored(self, data=None, write=True):
        """Verified content, with its object in the bucket unless told otherwise."""
        data = data or self.unique_bytes()
        content = self.contents._new_pending()
        if write:
            laboratory_bucket.write(content.object_key, iter([data]))
        return content._settle(hashlib.sha256(data).hexdigest(), len(data))

    def object_of_no_content(self):
        key = laboratory_bucket.new_object_key()
        laboratory_bucket.write(key, iter([self.unique_bytes()]))
        return key

    def test_the_first_run_marks_the_bucket_as_this_databases(self):
        self.reconcile(days_later=0)

        uuid_ = self.env[MODEL_IR_CONFIG_PARAMETER].sudo().get_str("database.uuid")
        self.assertEqual(laboratory_bucket.read_text(MARKER_KEY), uuid_)

    def test_an_object_of_no_content_is_deleted_once_a_day_old(self):
        key = self.object_of_no_content()

        self.reconcile(days_later=0)
        self.assertTrue(self.exists(key))
        self.reconcile()

        self.assertFalse(self.exists(key))

    def test_the_objects_of_duplicate_and_failed_content_left_in_the_bucket_are_deleted(self):
        data = self.unique_bytes()
        verified = self.stored(data)
        duplicate = self.contents._new_pending()
        laboratory_bucket.write(duplicate.object_key, iter([data]))
        duplicate._settle(hashlib.sha256(data).hexdigest(), len(data))
        failed = self.contents._new_pending()
        laboratory_bucket.write(failed.object_key, iter([self.unique_bytes()]))
        failed._fail()

        self.reconcile()

        self.assertEqual((duplicate.state, failed.state), ("duplicate", "failed"))
        self.assertFalse(self.exists(duplicate.object_key))
        self.assertFalse(self.exists(failed.object_key))
        self.assertTrue(self.exists(verified.object_key))

    def test_a_verified_object_is_never_deleted(self):
        content = self.stored()

        self.reconcile(days_later=30)

        self.assertTrue(self.exists(content.object_key))
        self.assertFalse(self.errors(content.object_key))

    def test_a_missing_verified_object_is_recorded_once(self):
        content = self.stored(write=False)

        self.reconcile()
        self.reconcile(days_later=3)

        self.assertEqual(len(self.errors(content.object_key)), 1)
        self.assertIn("is missing", self.errors(content.object_key).note)

    def test_a_verified_object_of_another_size_is_recorded(self):
        content = self.stored()
        laboratory_bucket.write_text(content.object_key, "other bytes")

        self.reconcile(days_later=0)

        self.assertIn(f"has 11 bytes instead of {content.size}", self.errors(content.object_key).note)

    def test_pending_content_of_no_open_upload_is_recorded_once_a_day_old(self):
        content = self.contents._new_pending()

        self.reconcile(days_later=0)
        self.assertFalse(self.errors(content.object_key))
        self.reconcile()

        self.assertIn("is still pending", self.errors(content.object_key).note)

    def test_the_content_and_multipart_upload_of_an_open_upload_are_left_alone(self):
        prepared = self.record(self.prepare(self.unique_bytes()).json()["upload"])
        refused = self.record(self.prepare(self.unique_bytes(), path="HPLC/run-02.csv").json()["upload"])
        # A refused upload may be finalized again once what refused it is gone, so it is still open.
        refused.sudo().write({"status": VERIFYING})
        refused.sudo().write({"status": REFUSED})

        self.reconcile()

        listed = {upload_id for _key, upload_id, _initiated in laboratory_bucket.multipart_uploads()}
        self.assertEqual(listed, {prepared.multipart_id, refused.multipart_id})
        self.assertFalse(self.errors(prepared.content_id.object_key))
        self.assertFalse(self.errors(refused.content_id.object_key))

    def test_the_multipart_upload_and_pending_content_of_an_ended_upload_are_handled(self):
        upload = self.record(self.prepare(self.unique_bytes()).json()["upload"])
        upload.sudo().write({"status": UPLOAD_EXPIRED})

        self.reconcile()

        self.assertFalse(list(laboratory_bucket.multipart_uploads()))
        self.assertIn("is still pending", self.errors(upload.content_id.object_key).note)

    def test_a_multipart_upload_of_no_upload_is_aborted_once_a_day_old(self):
        upload_id = laboratory_bucket.create_upload(laboratory_bucket.new_object_key())

        self.reconcile(days_later=0)
        self.assertEqual([upload for _key, upload, _initiated in laboratory_bucket.multipart_uploads()], [upload_id])
        self.reconcile()

        self.assertFalse(list(laboratory_bucket.multipart_uploads()))

    def test_a_bucket_of_another_database_is_left_alone_and_recorded_once(self):
        laboratory_bucket.write_text(MARKER_KEY, "another-database")
        key = self.object_of_no_content()

        self.reconcile()
        self.reconcile(days_later=3)

        self.assertTrue(self.exists(key))
        self.assertEqual(laboratory_bucket.read_text(MARKER_KEY), "another-database")
        self.assertEqual(len(self.errors("another-database")), 1)
