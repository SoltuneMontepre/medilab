import hashlib
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .laboratory_files_case import stored_content
from .laboratory_upload_race_case import LaboratoryUploadRaceCase
from odoo.addons.sol_laboratory.constants.laboratory_files import CONFLICT, RESTORED, SYNCED
from odoo.addons.sol_laboratory.constants.laboratory_uploads import UPLOAD_CONFLICT, VERIFYING
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_JOB_ITEM,
    MODEL_LABORATORY_CONTENT,
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FOLDER,
    MODEL_LABORATORY_UPLOAD,
)
from odoo.addons.sol_laboratory.services import laboratory_bucket

RUN = b"mau,Pb\nLAB-26-0412,0.012\n"


@tagged("post_install", "-at_install")
class TestLaboratoryUploadConcurrency(LaboratoryUploadRaceCase):
    """Two real database transactions preparing, finalizing or storing uploads at once, the second one through Odoo's
    request retrying. What the tests commit, and write to the bucket, is theirs to remove."""

    def uploads(self, env):
        return env[MODEL_LABORATORY_UPLOAD].with_user(self.tester(env))

    def prepare_upload(self, env, key="run-01-upload"):
        tester = self.tester(env)
        return self.uploads(env)._prepare(
            env[MODEL_LABORATORY_DEVICE].browse(self.device_id),
            env[MODEL_LABORATORY_FOLDER].with_user(tester).browse(self.folder_id),
            "HPLC/run-01.csv",
            len(RUN),
            hashlib.sha256(RUN).hexdigest(),
            self.first_id,
            key,
        )

    def uploaded(self, env):
        """A prepared upload whose one part is uploaded."""
        upload = self.prepare_upload(env).sudo()
        bucket, client = laboratory_bucket._calls()
        client.upload_part(
            Bucket=bucket.name,
            Key=upload.content_id.object_key,
            UploadId=upload.multipart_id,
            PartNumber=1,
            Body=RUN,
        )
        return upload.id

    def test_two_finalizations_of_one_upload_at_once_queue_one_verification(self):
        upload_id = self.committed(self.uploaded)

        def finalize(env):
            return self.uploads(env).browse(upload_id)._finalize()

        attempts, _upload = self.race(finalize, finalize)

        def work(env):
            items = env[MODEL_JOB_ITEM].search(
                [("document_model", "=", MODEL_LABORATORY_UPLOAD), ("document_id", "=", upload_id)]
            )
            return env[MODEL_LABORATORY_UPLOAD].browse(upload_id).status, len(items)

        self.assertEqual(attempts, 2)
        self.assertEqual(self.committed(work), (VERIFYING, 1))

    def test_two_prepares_with_one_idempotency_key_at_once_make_one_upload(self):
        attempts, upload_id = self.race(self.prepare_upload, self.prepare_upload)

        def work(env):
            uploads = env[MODEL_LABORATORY_UPLOAD].search([("folder_id", "=", self.folder_id)])
            for content in env[MODEL_LABORATORY_CONTENT].search([("id", ">", self.last_content_id)]):
                upload = uploads.filtered(lambda record, content=content: record.content_id == content)
                if upload.multipart_id:
                    laboratory_bucket.abort_upload(content.object_key, upload.multipart_id)
            return uploads.ids

        self.assertEqual(attempts, 2)
        self.assertEqual(self.committed(work), [upload_id])

    def test_storing_an_upload_and_restoring_the_file_at_once_get_the_next_two_numbers(self):
        def verified(env):
            content = stored_content(env, RUN.decode())
            return (
                env[MODEL_LABORATORY_UPLOAD]
                .sudo()
                .create(
                    {
                        "folder_id": self.folder_id,
                        "file_id": self.file_id,
                        "path": "HPLC/run-01.csv",
                        "base_version_id": self.first_id,
                        "claimed_size": content.size,
                        "claimed_sha256": content.sha256,
                        "content_id": content.id,
                        "status": VERIFYING,
                        "user_id": self.tester_id,
                        "device_id": self.device_id,
                        "expires_at": fields.Datetime.now() + timedelta(hours=1),
                    }
                )
                .id
            )

        upload_id = self.committed(verified)

        def restore(env):
            file = env[MODEL_LABORATORY_FILE].browse(self.file_id)
            first = file.version_ids.filtered(lambda version: version.id == self.first_id)
            return file._add_version(source=RESTORED, user=self.tester(env), restored_from=first)

        def store(env):
            upload = env[MODEL_LABORATORY_UPLOAD].browse(upload_id)
            upload._store()
            return upload

        attempts, _upload = self.race(restore, store)

        def work(env):
            file = env[MODEL_LABORATORY_FILE].browse(self.file_id)
            upload = env[MODEL_LABORATORY_UPLOAD].browse(upload_id)
            return [(version.number, version.source) for version in file.version_ids.sorted("number")], (
                upload.status,
                upload.version_id.number,
            )

        self.assertEqual(attempts, 2)
        # The upload was made from version 1, which was no longer current once the restore committed.
        self.assertEqual(self.committed(work), ([(1, SYNCED), (2, RESTORED), (3, CONFLICT)], (UPLOAD_CONFLICT, 3)))
