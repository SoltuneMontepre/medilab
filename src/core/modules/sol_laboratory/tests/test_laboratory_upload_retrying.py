from types import SimpleNamespace

from odoo.exceptions import ConcurrencyError
from odoo.http import retrying
from odoo.tests import tagged
from odoo.tools import mute_logger

from .laboratory_upload_case import LaboratoryUploadCase
from odoo.addons.sol_laboratory.constants.laboratory_uploads import PREPARED, VERIFY_JOB, VERIFYING
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_AUDIT_ENTRY,
    MODEL_JOB_ITEM,
    MODEL_LABORATORY_CONTENT,
    MODEL_LABORATORY_UPLOAD,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.sol_laboratory.services import laboratory_bucket

RUN = b"mau,Pb\nLAB-26-0412,0.012\n"


@tagged("post_install", "-at_install")
class TestLaboratoryUploadRetrying(LaboratoryUploadCase):
    """Odoo's request retrying inside real requests of the upload routes: a request that fails on concurrency after its
    bucket calls runs again from authenticating the key, and what it does counts once."""

    def setUp(self):
        super().setUp()
        # Odoo waits a random time before each new try; these tests do not.
        self.patch(retrying, "random", SimpleNamespace(uniform=lambda _low, _high: 0))

    def fail_once(self, method_name):
        """Make the upload's method fail on concurrency on its first run, after what the request did before it, as a
        concurrent request would; the number of times it ran is kept."""
        uploads = type(self.env[MODEL_LABORATORY_UPLOAD])
        method = getattr(uploads, method_name)
        runs = []

        def failing(*args, **kwargs):
            runs.append(1)
            if len(runs) == 1:
                raise ConcurrencyError("A concurrent request changed the same records.")
            return method(*args, **kwargs)

        self.patch(uploads, method_name, failing)
        return runs

    def test_preparing_run_again_after_its_multipart_upload_was_created_makes_one_upload(self):
        created = []
        create_upload = laboratory_bucket.create_upload

        def recording(key):
            upload_id = create_upload(key)
            created.append((key, upload_id))
            self.addCleanup(laboratory_bucket.abort_upload, key, upload_id)
            return upload_id

        self.patch(laboratory_bucket, "create_upload", recording)
        runs = self.fail_once("_create_once")

        with mute_logger("odoo.http"):
            response = self.prepare(RUN, idempotency_key="run-01-upload")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((len(runs), len(created)), (2, 2))
        uploads = self.env[MODEL_LABORATORY_UPLOAD].sudo().search([("idempotency_key", "=", "run-01-upload")])
        self.assertEqual((len(uploads), uploads.status), (1, PREPARED))
        keys = self.env[MODEL_LABORATORY_CONTENT].sudo().search([]).mapped("object_key")
        # The first try's multipart upload has no content that counts; reconciliation aborts it.
        self.assertNotIn(created[0][0], keys)
        self.assertEqual(uploads.content_id.object_key, created[1][0])
        self.assertEqual(len(self.entries_of(uploads)), 1)

    def test_finalizing_run_again_queues_one_verification(self):
        upload = self.prepare(RUN).json()["upload"]
        self.put_parts(upload, RUN)
        runs = self.fail_once("_queue")

        with mute_logger("odoo.http"):
            response = self.finalize(upload)

        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(len(runs), 2)
        record = self.record(upload)
        job = self.env[MODEL_SCHEDULED_JOB]._by_key(VERIFY_JOB)
        items = self.env[MODEL_JOB_ITEM].search([("job_id", "=", job.id), ("document_id", "=", record.id)])
        self.assertEqual((record.status, len(items)), (VERIFYING, 1))
        self.assertEqual(len(self.entries_of(record)), 2)

    def entries_of(self, upload):
        return (
            self.env[MODEL_AUDIT_ENTRY]
            .sudo()
            .search([("document_model", "=", upload._name), ("document_id", "=", upload.id)])
        )
