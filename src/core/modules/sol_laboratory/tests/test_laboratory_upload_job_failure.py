from odoo.tests import tagged
from odoo.tools import mute_logger

from .laboratory_upload_case import LaboratoryUploadCase
from odoo.addons.sol_laboratory.constants.laboratory_files import FAILED, VERIFIED
from odoo.addons.sol_laboratory.constants.laboratory_uploads import (
    STORE_JOB,
    STORING_FAILED,
    UPLOAD_FAILED,
    VERIFICATION_FAILED,
    VERIFY_JOB,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_UPLOAD, MODEL_SCHEDULED_JOB

RUN = b"mau,Pb\nLAB-26-0412,0.012\n"


@tagged("post_install", "-at_install")
class TestLaboratoryUploadJobFailure(LaboratoryUploadCase):
    """An upload whose verification or storing fails its job's last attempt ends failed, so the computer stops waiting
    for it."""

    def finalized(self):
        upload = self.prepare(RUN).json()["upload"]
        self.put_parts(upload, RUN)
        self.assertEqual(self.finalize(upload).status_code, 202)
        return upload

    def break_job(self, key, method_name):
        """Make the job give up after one attempt, and the upload's method fail on it."""
        self.env[MODEL_SCHEDULED_JOB]._by_key(key).max_attempts = 1

        def failing(*args, **kwargs):
            raise RuntimeError("The bucket did not answer.")

        self.patch(type(self.env[MODEL_LABORATORY_UPLOAD]), method_name, failing)

    def test_a_verification_that_fails_for_good_fails_the_upload_and_its_content(self):
        upload = self.finalized()
        self.break_job(VERIFY_JOB, "_verify")

        with mute_logger("odoo.addons.sol_laboratory.models.system.scheduled_job"):
            self.run_jobs()

        record = self.record(upload)
        self.assertEqual((record.status, record.failure_code), (UPLOAD_FAILED, VERIFICATION_FAILED))
        self.assertEqual(record.content_id.state, FAILED)
        self.assertEqual(self.read_upload(upload)["failure_code"], VERIFICATION_FAILED)

    def test_a_storing_that_fails_for_good_fails_the_upload_and_keeps_its_verified_content(self):
        upload = self.finalized()
        self.break_job(STORE_JOB, "_store")

        with mute_logger("odoo.addons.sol_laboratory.models.system.scheduled_job"):
            self.run_jobs()

        record = self.record(upload)
        self.assertEqual((record.status, record.failure_code), (UPLOAD_FAILED, STORING_FAILED))
        self.assertEqual(record.content_id.state, VERIFIED)
