import hashlib
import uuid

from .laboratory_api_case import LaboratoryApiCase
from .laboratory_bucket_case import LaboratoryBucketTools, remove_written_objects
from odoo.addons.sol_laboratory.constants.laboratory_bucket import PART_SIZE
from odoo.addons.sol_laboratory.constants.laboratory_uploads import STORE_JOB, VERIFY_JOB
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_UPLOAD, MODEL_SCHEDULED_JOB


class LaboratoryUploadCase(LaboratoryBucketTools, LaboratoryApiCase):
    """A tester's computer uploading files of the HPLC folder through the laboratory files API, straight to the bucket
    of local development and CI, and the jobs that verify and store them."""

    def setUp(self):
        super().setUp()
        remove_written_objects(self)
        self.key = self.signed_in_key(self.tester, "hplc-installation")

    def prepare(self, data, path="HPLC/run-01.csv", key=None, folder=None, base_version=None, idempotency_key=None):
        """Prepare the upload of the bytes, as Medilab Sync does, and return the answer."""
        body = {"path": path, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        if base_version is not None:
            body["base_version_id"] = base_version.id
        headers = {"Idempotency-Key": idempotency_key or uuid.uuid4().hex}
        folder = folder or self.folder
        return self.api("POST", f"/folders/{folder.id}/uploads", body, key=key or self.key, headers=headers)

    def put_parts(self, upload, data, key=None, folder=None):
        """Upload the bytes in the upload's parts through the addresses the API gives."""
        folder = folder or self.folder
        count = upload["part_count"]
        if not count:
            return
        response = self.api(
            "POST",
            f"/folders/{folder.id}/uploads/{upload['id']}/parts",
            {"part_numbers": list(range(1, count + 1))},
            key=key or self.key,
        )
        self.assertEqual(response.status_code, 200, response.text)
        for part in response.json()["parts"]:
            start = (part["number"] - 1) * PART_SIZE
            answer = self.call_presigned("PUT", part["url"], data[start : start + PART_SIZE])
            self.assertEqual(answer.status_code, 200, answer.text)

    def finalize(self, upload, key=None, folder=None):
        folder = folder or self.folder
        return self.api("POST", f"/folders/{folder.id}/uploads/{upload['id']}/finalize", key=key or self.key)

    def read_upload(self, upload, key=None, folder=None):
        folder = folder or self.folder
        response = self.api("GET", f"/folders/{folder.id}/uploads/{upload['id']}", key=key or self.key)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["upload"]

    def run_jobs(self):
        """Run a batch of the verification and of the storing of uploads, as their crons do."""
        jobs = self.env[MODEL_SCHEDULED_JOB]
        jobs._run_key(VERIFY_JOB)
        jobs._run_key(STORE_JOB)
        self.env.invalidate_all()

    def upload(self, data, path="HPLC/run-01.csv", key=None, folder=None, base_version=None):
        """Upload the bytes from preparing to storing and return the upload as the computer reads it at the end."""
        response = self.prepare(data, path, key=key, folder=folder, base_version=base_version)
        self.assertEqual(response.status_code, 200, response.text)
        upload = response.json()["upload"]
        self.put_parts(upload, data, key=key, folder=folder)
        finalized = self.finalize(upload, key=key, folder=folder)
        self.assertEqual(finalized.status_code, 202, finalized.text)
        self.run_jobs()
        return self.read_upload(upload, key=key, folder=folder)

    def record(self, upload):
        return self.env[MODEL_LABORATORY_UPLOAD].sudo().browse(upload["id"])
