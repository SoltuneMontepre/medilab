import contextlib
import hashlib
import os
import time
from datetime import timedelta

import psycopg2

from odoo import fields, sql_db
from odoo.tests import tagged
from odoo.tools import mute_logger

from .laboratory_upload_race_case import LaboratoryUploadRaceCase
from odoo.addons.sol_laboratory.constants.laboratory_bucket import READ_CHUNK_SIZE
from odoo.addons.sol_laboratory.constants.laboratory_files import PENDING, VERIFIED
from odoo.addons.sol_laboratory.constants.laboratory_uploads import COMPLETED, STORE_JOB, VERIFY_JOB, VERIFYING
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_IR_CRON_PROGRESS,
    MODEL_JOB_ITEM,
    MODEL_LABORATORY_CONTENT,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_UPLOAD,
    MODEL_SCHEDULED_JOB,
)
from odoo.addons.sol_laboratory.models.system.scheduled_job import CRON_PASS_KEY, CRON_PROGRESS_KEY
from odoo.addons.sol_laboratory.services import laboratory_bucket

# Two chunks of reading, so a verification can stop between them.
DATA = os.urandom(READ_CHUNK_SIZE + 1000)


@tagged("post_install", "-at_install")
class TestLaboratoryUploadVerification(LaboratoryUploadRaceCase):
    """A verification of an upload stopped midway by a killed worker, on a real connection under the cron: the content
    stays pending, the item is claimed again after the claim timeout, the object is read from the first byte again,
    and one version is stored."""

    def setUp(self):
        super().setUp()
        self.upload_id = self.committed(self.finalized)
        self.reads = []
        self.read = laboratory_bucket.read

    def finalized(self, env):
        # Its object written as the server writes small content, so a test needs no part addresses.
        content = env[MODEL_LABORATORY_CONTENT]._new_pending()
        laboratory_bucket.write(content.object_key, iter([DATA]))
        upload = env[MODEL_LABORATORY_UPLOAD].create(
            {
                "folder_id": self.folder_id,
                "file_id": self.file_id,
                "path": "HPLC/run-01.csv",
                "base_version_id": self.first_id,
                "claimed_size": len(DATA),
                "claimed_sha256": hashlib.sha256(DATA).hexdigest(),
                "content_id": content.id,
                "status": VERIFYING,
                "user_id": self.tester_id,
                "device_id": self.device_id,
                "expires_at": fields.Datetime.now() + timedelta(hours=1),
                "finalized_at": fields.Datetime.now(),
            }
        )
        env[MODEL_SCHEDULED_JOB].queue(VERIFY_JOB, f"content:{content.id}", document=upload)
        return upload.id

    def reading(self, kill=None):
        """Read objects as the bucket does, recording the bytes each reading got; with kill, the connection of the
        batch ends after the first chunk, as when the worker is killed."""

        @contextlib.contextmanager
        def recording(key):
            got = []
            self.reads.append(got)
            with self.read(key) as chunks:

                def counted():
                    for chunk in chunks:
                        got.append(len(chunk))
                        yield chunk
                        if kill:
                            kill.execute("SELECT pg_terminate_backend(pg_backend_pid())")

                yield counted()

        self.patch(laboratory_bucket, "read", recording)

    def run_batch(self, env, key=VERIFY_JOB):
        """One batch of the job with the context Odoo's cron gives it."""
        job = env[MODEL_SCHEDULED_JOB]._by_key(key)
        progress = env[MODEL_IR_CRON_PROGRESS].create({"cron_id": job.cron_id.id})
        context = {CRON_PROGRESS_KEY: progress.id, "cron_id": job.cron_id.id, CRON_PASS_KEY: time.monotonic() + 120}
        job.with_context(**context)._run_batch()

    def killed_batch(self):
        cursor = sql_db.db_connect(self.registry.db_name).cursor()
        self.reading(kill=cursor)
        try:
            with mute_logger("odoo.sql_db"), self.assertRaises(psycopg2.Error):
                self.run_batch(self.environment(cursor))
        finally:
            # The batch died in an item's savepoint, which its connection can no longer release.
            cursor.transaction = None
            cursor.close()

    def state(self):
        def work(env):
            upload = env[MODEL_LABORATORY_UPLOAD].browse(self.upload_id)
            item = env[MODEL_JOB_ITEM].search([("document_id", "=", upload.id), ("item_key", "=like", "content:%")])
            versions = env[MODEL_LABORATORY_FILE].browse(self.file_id).version_ids
            return upload.status, upload.content_id.state, item.status, item.attempts, len(versions)

        return self.committed(work)

    def test_a_verification_killed_midway_restarts_from_the_first_byte_and_stores_one_version(self):
        self.killed_batch()
        self.assertEqual(self.state(), (VERIFYING, PENDING, "running", 0, 1))
        self.assertEqual(self.reads, [[READ_CHUNK_SIZE]])

        def past_claim_timeout(env):
            item = env[MODEL_JOB_ITEM].search(
                [("document_id", "=", self.upload_id), ("item_key", "=like", "content:%")]
            )
            claim_timeout = env[MODEL_SCHEDULED_JOB]._by_key(VERIFY_JOB).claim_timeout_minutes
            item.write({"claimed_at": fields.Datetime.now() - timedelta(minutes=claim_timeout + 1)})

        self.committed(past_claim_timeout)
        self.reading()
        self.committed(self.run_batch)
        self.assertEqual(self.state(), (VERIFYING, PENDING, "pending", 1, 1))

        def due(env):
            env[MODEL_JOB_ITEM].search([("document_id", "=", self.upload_id)]).write(
                {"next_attempt_at": fields.Datetime.now()}
            )

        self.committed(due)
        self.committed(self.run_batch)
        self.committed(lambda env: self.run_batch(env, STORE_JOB))

        self.assertEqual(self.reads[1], [READ_CHUNK_SIZE, 1000])
        self.assertEqual(self.state(), (COMPLETED, VERIFIED, "done", 1, 2))
