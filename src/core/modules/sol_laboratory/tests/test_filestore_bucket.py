import contextlib
import io
import os
from unittest.mock import patch

from odoo import api, sql_db
from odoo.api import SUPERUSER_ID
from odoo.orm.environments import Transaction
from odoo.tests import tagged
from odoo.tools import config, file_open

from .laboratory_bucket_case import LaboratoryBucketCase
from .test_module_files import MODULE_IMAGE
from odoo.addons.sol_laboratory.constants.laboratory_bucket import FILESTORE_VARIABLE
from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ATTACHMENT
from odoo.addons.sol_laboratory.services import laboratory_bucket

BUNDLE_VERSION = "0000000"
BUNDLE_FILE = "web.assets_test.min.js"
# Every object of the bucket counts as older than the cleanup's grace period.
ALL_OLD = patch("odoo.addons.sol_laboratory.models.system.ir_attachment.FILESTORE_GC_GRACE", -60)


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

    def orphan_object(self, content):
        """An object of the bucket that no attachment uses any more, as a deleted attachment leaves it."""
        attachment = self.new_attachment(content)
        key = self.attachments._bucket_key(attachment.store_fname)
        attachment.unlink()
        return key

    def run_cleanup(self):
        # The cleanup reads the attachments through a cursor of its own, which sees the test's only in test mode.
        with self.registry_test_mode(), self.registry.cursor() as cursor:
            self.attachments.with_env(self.env(cr=cursor))._gc_filestore_bucket()

    @contextlib.contextmanager
    def other_transaction(self):
        """An environment on a database transaction of its own, rolled back at the end."""
        with sql_db.db_connect(self.registry.db_name).cursor() as cursor:
            # An environment looks its registry up by name, which waits on the lock the test run holds.
            cursor.transaction = Transaction(self.registry)
            cursor.transaction._check_signaling(cursor)
            try:
                yield api.Environment(cursor, SUPERUSER_ID, {})
            finally:
                cursor.transaction = None
                cursor.rollback()

    def test_a_new_file_is_written_to_the_bucket(self):
        content = os.urandom(5000)

        attachment = self.new_attachment(content)

        key = self.attachments._bucket_key(attachment.store_fname)
        self.assertEqual(laboratory_bucket.object_size(key), len(content))

    def test_a_file_odoo_uploads_is_written_to_the_bucket(self):
        content = os.urandom(5000)

        attachment = self.attachments._upload_file(io.BytesIO(content), {"name": "file.bin"})
        key = self.attachments._bucket_key(attachment.store_fname)
        self.addCleanup(laboratory_bucket.delete, key)

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

    def asset_bundle(self, content=b"console.log('bundle');"):
        bundle = self.attachments.create(
            {
                "name": BUNDLE_FILE,
                "raw": content,
                "public": True,
                "url": f"/web/assets/{BUNDLE_VERSION}/{BUNDLE_FILE}",
                "res_model": "ir.ui.view",
                "res_id": 0,
            }
        )
        self.addCleanup(laboratory_bucket.delete, self.attachments._bucket_key(bundle.store_fname))
        return bundle

    def test_an_asset_bundle_whose_file_is_lost_is_deleted_so_it_is_built_again(self):
        bundle = self.asset_bundle()
        url = bundle.url
        self.remove_local_copy(bundle)
        laboratory_bucket.delete(self.attachments._bucket_key(bundle.store_fname))

        with self.assertLogs("odoo.addons.sol_laboratory.models.system.ir_attachment", "WARNING") as logs:
            self.attachments._drop_lost_asset_bundle(BUNDLE_FILE, BUNDLE_VERSION, {})

        self.assertFalse(bundle.exists())
        self.assertIn(url, logs.output[-1])

    def lose(self, attachment):
        self.remove_local_copy(attachment)
        laboratory_bucket.delete(self.attachments._bucket_key(attachment.store_fname))

    def test_every_lost_attachment_of_a_bundle_built_twice_is_deleted(self):
        first = self.asset_bundle()
        second = self.asset_bundle()
        self.lose(first)

        with self.assertLogs("odoo.addons.sol_laboratory.models.system.ir_attachment", "WARNING"):
            self.attachments._drop_lost_asset_bundle(BUNDLE_FILE, BUNDLE_VERSION, {})

        self.assertFalse((first | second).exists())

    def test_a_lost_attachment_is_deleted_and_one_with_its_file_kept_at_the_same_address(self):
        lost = self.asset_bundle(b"console.log('lost');")
        kept = self.asset_bundle(b"console.log('kept');")
        self.lose(lost)

        with self.assertLogs("odoo.addons.sol_laboratory.models.system.ir_attachment", "WARNING"):
            self.attachments._drop_lost_asset_bundle(BUNDLE_FILE, BUNDLE_VERSION, {})

        self.assertFalse(lost.exists())
        self.assertTrue(kept.exists())

    def test_a_lost_bundle_asked_for_at_any_version_is_deleted(self):
        bundle = self.asset_bundle()
        self.lose(bundle)

        with self.assertLogs("odoo.addons.sol_laboratory.models.system.ir_attachment", "WARNING"):
            self.attachments._drop_lost_asset_bundle(BUNDLE_FILE, "any", {})

        self.assertFalse(bundle.exists())

    def test_an_asset_bundle_whose_file_the_bucket_holds_is_kept_and_read_from_it(self):
        bundle = self.asset_bundle()
        self.remove_local_copy(bundle)

        self.attachments._drop_lost_asset_bundle(BUNDLE_FILE, BUNDLE_VERSION, {})

        self.assertTrue(bundle.exists())
        self.assertTrue(os.path.exists(self.attachments._full_path(bundle.store_fname)))

    def test_a_debug_asset_address_names_no_bundle_to_delete(self):
        bundle = self.asset_bundle()
        self.remove_local_copy(bundle)
        laboratory_bucket.delete(self.attachments._bucket_key(bundle.store_fname))

        self.attachments._drop_lost_asset_bundle(BUNDLE_FILE, "debug", {})

        self.assertTrue(bundle.exists())

    def test_an_install_or_update_deletes_the_asset_bundles_so_they_are_built_again(self):
        bundle = self.asset_bundle()

        with patch.dict(config._runtime_options, {"update": ["sol_laboratory"]}):
            self.attachments._register_hook()

        self.assertFalse(bundle.exists())

    def test_a_server_that_neither_installs_nor_updates_keeps_the_asset_bundles(self):
        bundle = self.asset_bundle()

        with patch.dict(config._runtime_options, {"init": [], "update": []}):
            self.attachments._register_hook()

        self.assertTrue(bundle.exists())

    def test_a_server_that_neither_installs_nor_updates_writes_nothing_at_start(self):
        with patch.dict(os.environ, {FILESTORE_VARIABLE: "0"}):
            attachment = self.new_attachment(os.urandom(100))

        with patch.dict(config._runtime_options, {"init": [], "update": []}):
            self.attachments._register_hook()

        self.assertIsNone(laboratory_bucket.object_size(self.attachments._bucket_key(attachment.store_fname)))

    def test_an_update_writes_a_module_file_lost_in_both_places_again(self):
        with file_open(MODULE_IMAGE, "rb") as file:
            content = file.read()
        attachment = self.new_attachment(content)
        self.remove_local_copy(attachment)
        laboratory_bucket.delete(self.attachments._bucket_key(attachment.store_fname))

        with patch.dict(config._runtime_options, {"update": ["sol_laboratory"]}):
            self.attachments._register_hook()

        key = self.attachments._bucket_key(attachment.store_fname)
        self.assertEqual(laboratory_bucket.object_size(key), len(content))
        self.assertTrue(os.path.exists(self.attachments._full_path(attachment.store_fname)))

    def test_a_file_the_bucket_holds_is_not_missing(self):
        attachment = self.new_attachment(os.urandom(100))
        self.remove_local_copy(attachment)

        self.assertNotIn(attachment, self.attachments._missing_files())

    def test_the_cleanup_deletes_old_objects_no_attachment_uses_and_keeps_the_rest(self):
        attachment = self.new_attachment(os.urandom(100))
        kept = self.attachments._bucket_key(attachment.store_fname)
        orphan = self.attachments._bucket_key("ff/" + "f" * 40)
        laboratory_bucket.write(orphan, [b"orphan"])
        self.addCleanup(laboratory_bucket.delete, orphan)

        with ALL_OLD:
            self.run_cleanup()

        self.assertIsNone(laboratory_bucket.object_size(orphan))
        self.assertIsNotNone(laboratory_bucket.object_size(kept))

    def test_the_cleanup_keeps_a_new_object_no_attachment_uses_yet(self):
        orphan = self.attachments._bucket_key("ee/" + "e" * 40)
        laboratory_bucket.write(orphan, [b"in flight"])
        self.addCleanup(laboratory_bucket.delete, orphan)

        self.run_cleanup()

        self.assertIsNotNone(laboratory_bucket.object_size(orphan))

    def test_the_cleanup_keeps_an_old_object_an_attachment_uses_again_while_it_runs(self):
        content = os.urandom(100)
        key = self.orphan_object(content)
        listing = laboratory_bucket.keys

        def listing_then_reuse(prefix):
            yield from listing(prefix)
            # An asset bundle built again with the same content finds its object in the bucket and uploads nothing.
            self.new_attachment(content)

        with ALL_OLD, patch.object(laboratory_bucket, "keys", listing_then_reuse):
            self.run_cleanup()

        self.assertEqual(laboratory_bucket.object_size(key), 100)

    def test_the_cleanup_leaves_an_old_object_a_transaction_in_progress_relies_on(self):
        content = os.urandom(100)
        key = self.orphan_object(content)

        with self.other_transaction() as env, ALL_OLD:
            env[MODEL_IR_ATTACHMENT].create({"name": "file.bin", "raw": content})
            self.run_cleanup()

        self.assertEqual(laboratory_bucket.object_size(key), 100)

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
