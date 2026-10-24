import os
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tools import config

from .laboratory_bucket_case import LaboratoryBucketCase
from odoo.addons.sol_laboratory.constants.laboratory_bucket import FILESTORE_VARIABLE
from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ATTACHMENT
from odoo.addons.sol_laboratory.services import laboratory_bucket


@tagged("post_install", "-at_install")
class TestFilestoreBucket(LaboratoryBucketCase):
    def setUp(self):
        super().setUp()
        self.bucket()
        self.attachments = self.env[MODEL_IR_ATTACHMENT].sudo()
        environment = patch.dict(os.environ, {FILESTORE_VARIABLE: "1"})
        environment.start()
        self.addCleanup(environment.stop)

    def new_attachment(self, content):
        attachment = self.attachments.create({"name": "file.bin", "raw": content})
        self.addCleanup(laboratory_bucket.delete, self.attachments._bucket_key(attachment.store_fname))
        return attachment

    def remove_local_copy(self, attachment):
        os.unlink(self.attachments._full_path(attachment.store_fname))

    def test_a_new_file_is_written_to_the_bucket(self):
        content = os.urandom(5000)

        attachment = self.new_attachment(content)

        key = self.attachments._bucket_key(attachment.store_fname)
        self.assertEqual(laboratory_bucket.object_size(key), len(content))

    def test_a_file_missing_on_this_server_is_read_from_the_bucket(self):
        content = os.urandom(5000)
        attachment = self.new_attachment(content)
        self.remove_local_copy(attachment)
        attachment.invalidate_recordset(["raw"])

        self.assertEqual(attachment.raw, content)
        self.assertTrue(os.path.exists(self.attachments._full_path(attachment.store_fname)))

    def test_a_file_missing_on_this_server_is_streamed_from_the_bucket(self):
        content = os.urandom(5000)
        attachment = self.new_attachment(content)
        self.remove_local_copy(attachment)

        stream = attachment._to_http_stream()

        self.assertEqual(stream.type, "path")
        with open(stream.path, "rb") as file:
            self.assertEqual(file.read(), content)

    def test_a_file_in_neither_place_reads_as_empty(self):
        attachment = self.new_attachment(os.urandom(100))
        self.remove_local_copy(attachment)
        laboratory_bucket.delete(self.attachments._bucket_key(attachment.store_fname))
        attachment.invalidate_recordset(["raw"])

        self.assertFalse(attachment.raw)

    def test_an_install_or_update_writes_the_files_odoo_wrote_before_this_module_loaded(self):
        content = os.urandom(3000)
        with patch.dict(os.environ, {FILESTORE_VARIABLE: "0"}):
            attachment = self.new_attachment(content)
        key = self.attachments._bucket_key(attachment.store_fname)
        self.assertIsNone(laboratory_bucket.object_size(key))

        with patch.dict(config._runtime_options, {"update": ["sol_laboratory"]}):
            self.attachments._register_hook()

        self.assertEqual(laboratory_bucket.object_size(key), len(content))

    def test_a_server_that_neither_installs_nor_updates_writes_nothing_at_start(self):
        with patch.dict(os.environ, {FILESTORE_VARIABLE: "0"}):
            attachment = self.new_attachment(os.urandom(100))

        with patch.dict(config._runtime_options, {"init": [], "update": []}):
            self.attachments._register_hook()

        self.assertIsNone(laboratory_bucket.object_size(self.attachments._bucket_key(attachment.store_fname)))

    def test_the_cleanup_deletes_old_objects_no_attachment_uses_and_keeps_the_rest(self):
        attachment = self.new_attachment(os.urandom(100))
        kept = self.attachments._bucket_key(attachment.store_fname)
        orphan = self.attachments._bucket_key("ff/" + "f" * 40)
        laboratory_bucket.write(orphan, [b"orphan"])
        self.addCleanup(laboratory_bucket.delete, orphan)

        with patch("odoo.addons.sol_laboratory.models.system.ir_attachment.FILESTORE_GC_GRACE", -60):
            self.attachments._gc_filestore_bucket()

        self.assertIsNone(laboratory_bucket.object_size(orphan))
        self.assertIsNotNone(laboratory_bucket.object_size(kept))

    def test_the_cleanup_keeps_a_new_object_no_attachment_uses_yet(self):
        orphan = self.attachments._bucket_key("ee/" + "e" * 40)
        laboratory_bucket.write(orphan, [b"in flight"])
        self.addCleanup(laboratory_bucket.delete, orphan)

        self.attachments._gc_filestore_bucket()

        self.assertIsNotNone(laboratory_bucket.object_size(orphan))

    def test_nothing_is_written_to_the_bucket_when_the_filestore_is_not_turned_on(self):
        with patch.dict(os.environ, {FILESTORE_VARIABLE: "0"}):
            attachment = self.new_attachment(os.urandom(100))

        self.assertIsNone(laboratory_bucket.object_size(self.attachments._bucket_key(attachment.store_fname)))
