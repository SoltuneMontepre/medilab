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

        self.assertEqual(bytes(attachment.raw), content)
        self.assertTrue(os.path.exists(self.attachments._full_path(attachment.store_fname)))

    def test_a_file_missing_on_this_server_is_streamed_from_the_bucket(self):
        content = os.urandom(5000)
        attachment = self.new_attachment(content)
        self.remove_local_copy(attachment)

        stream = attachment._to_http_stream()

        self.assertEqual(stream.type, "path")
        with open(stream.path, "rb") as file:
            self.assertEqual(file.read(), content)

    def test_a_file_in_neither_place_reads_as_empty_and_is_logged(self):
        attachment = self.new_attachment(os.urandom(100))
        self.remove_local_copy(attachment)
        laboratory_bucket.delete(self.attachments._bucket_key(attachment.store_fname))
        attachment.invalidate_recordset(["raw"])

        with self.assertLogs("odoo.addons.sol_laboratory.models.system.ir_attachment", "WARNING") as logs:
            content = attachment.raw

        self.assertFalse(content)
        self.assertIn(attachment.store_fname, logs.output[0])

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

    def mounted_copy(self, attachment, content):
        """Leave the file only where the bucket mounted as the filestore wrote it: at the root, under the database."""
        key = f"{self.env.cr.dbname}/{attachment.store_fname}"
        laboratory_bucket.write(key, [content])
        self.addCleanup(laboratory_bucket.delete, key)
        laboratory_bucket.delete(self.attachments._bucket_key(attachment.store_fname))
        self.remove_local_copy(attachment)
        return key

    def test_a_file_the_mounted_bucket_wrote_is_moved_under_the_filestore_and_read(self):
        content = os.urandom(5000)
        attachment = self.new_attachment(content)
        mounted = self.mounted_copy(attachment, content)

        self.attachments._move_mounted_files()
        attachment.invalidate_recordset(["raw"])

        self.assertEqual(bytes(attachment.raw), content)
        self.assertIsNone(laboratory_bucket.object_size(mounted))

    def test_moving_keeps_a_file_already_under_the_filestore_and_removes_the_mounted_one(self):
        content = os.urandom(100)
        attachment = self.new_attachment(content)
        mounted = f"{self.env.cr.dbname}/{attachment.store_fname}"
        laboratory_bucket.write(mounted, [content])
        self.addCleanup(laboratory_bucket.delete, mounted)

        self.attachments._move_mounted_files()

        self.assertEqual(laboratory_bucket.object_size(self.attachments._bucket_key(attachment.store_fname)), 100)
        self.assertIsNone(laboratory_bucket.object_size(mounted))

    def test_moving_leaves_objects_that_are_not_stored_files(self):
        other = f"{self.env.cr.dbname}/checklist/ab/" + "a" * 40
        laboratory_bucket.write(other, [b""])
        self.addCleanup(laboratory_bucket.delete, other)

        self.attachments._move_mounted_files()

        self.assertIsNotNone(laboratory_bucket.object_size(other))

    def test_nothing_is_written_to_the_bucket_when_the_filestore_is_not_turned_on(self):
        with patch.dict(os.environ, {FILESTORE_VARIABLE: "0"}):
            attachment = self.new_attachment(os.urandom(100))

        self.assertIsNone(laboratory_bucket.object_size(self.attachments._bucket_key(attachment.store_fname)))
