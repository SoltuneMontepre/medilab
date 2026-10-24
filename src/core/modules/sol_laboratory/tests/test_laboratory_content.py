import hashlib
import re

from psycopg2 import IntegrityError

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import SQL, mute_logger

from .laboratory_bucket_case import LaboratoryBucketCase
from odoo.addons.sol_laboratory.constants.laboratory_files import DUPLICATE, FAILED, PENDING, VERIFIED
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_CONTENT
from odoo.addons.sol_laboratory.services import laboratory_bucket

# Bytes no demo file has, so no content of them is stored before a test.
DATA = "Kết quả HPLC của bài kiểm tra nội dung".encode()
SHA256 = hashlib.sha256(DATA).hexdigest()


@tagged("post_install", "-at_install")
class TestLaboratoryContent(LaboratoryBucketCase):
    """Stored content: one object of the bucket, counted once the server has computed its size and SHA-256."""

    def setUp(self):
        super().setUp()
        self.contents = self.env[MODEL_LABORATORY_CONTENT].sudo()

    def written(self, data=DATA):
        """New pending content whose object holds the data, deleted after the test."""
        content = self.contents._new_pending()
        self.addCleanup(laboratory_bucket.delete, content.object_key)
        laboratory_bucket.write(content.object_key, iter([data]))
        return content

    def commit_hooks(self):
        """Run what the transaction does once it commits, as the tests never commit."""
        self.env.cr.postcommit.run()

    def test_new_content_is_pending_under_a_random_key_that_tells_nothing_about_it(self):
        first, second = self.contents._new_pending(), self.contents._new_pending()

        self.assertEqual((first.state, first.sha256, first.size), (PENDING, False, False))
        self.assertNotEqual(first.object_key, second.object_key)
        self.assertTrue(re.fullmatch(r"[0-9a-f]{32}", first.object_key))

    def test_nobody_records_content_with_a_hash_or_a_state_of_their_own(self):
        for values in ({"state": VERIFIED}, {"sha256": SHA256}, {"size": len(DATA)}):
            with self.subTest(values=values), self.assertRaises(UserError):
                self.contents.create({"object_key": laboratory_bucket.new_object_key(), **values})

    def test_settled_content_is_verified_and_never_changed_or_deleted(self):
        content = self.written()

        settled = content._settle(SHA256, len(DATA))

        self.assertEqual(settled, content)
        self.assertEqual((content.state, content.sha256, content.size), (VERIFIED, SHA256, len(DATA)))
        for values in ({"state": PENDING}, {"sha256": "0" * 64}, {"size": 1}, {"object_key": "0" * 32}):
            with self.subTest(values=values), self.assertRaises(UserError):
                content.write(values)
        with self.assertRaises(UserError):
            content.unlink()
        self.assertEqual(content._settle(SHA256, len(DATA)), content)

    def test_content_already_stored_is_a_duplicate_whose_object_is_deleted_once_committed(self):
        stored = self.written()._settle(SHA256, len(DATA))
        again = self.written()

        settled = again._settle(SHA256, len(DATA))

        self.assertEqual(settled, stored)
        self.assertEqual((again.state, again.sha256, again.size), (DUPLICATE, SHA256, len(DATA)))
        self.assertEqual(laboratory_bucket.object_size(again.object_key), len(DATA))
        self.commit_hooks()
        self.assertIsNone(laboratory_bucket.object_size(again.object_key))
        self.assertEqual(laboratory_bucket.object_size(stored.object_key), len(DATA))
        self.assertEqual(again._settle(SHA256, len(DATA)), stored)

    def test_failed_content_is_never_verified_and_its_object_is_deleted_once_committed(self):
        content = self.written()

        content._fail()

        self.assertEqual(content.state, FAILED)
        with self.assertRaises(UserError):
            content._settle(SHA256, len(DATA))
        self.commit_hooks()
        self.assertIsNone(laboratory_bucket.object_size(content.object_key))

    def test_verified_content_never_fails(self):
        content = self.written()._settle(SHA256, len(DATA))

        with self.assertRaises(UserError):
            content._fail()

        self.assertEqual(content.state, VERIFIED)

    def test_the_database_keeps_one_verified_content_per_sha256(self):
        self.written()._settle(SHA256, len(DATA))
        other = self.contents._new_pending()
        other.flush_recordset()

        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.env.cr.execute(
                "UPDATE medilab_laboratory_content SET state = %s, sha256 = %s, size = %s WHERE id = %s",
                [VERIFIED, SHA256, len(DATA), other.id],
            )

    def test_verified_content_has_its_size_and_sha256_and_keys_are_32_hexadecimal_digits(self):
        content = self.contents._new_pending()
        content.flush_recordset()
        refused = (
            ("state = %s", [VERIFIED]),
            ("object_key = %s", ["A" * 32]),
            ("sha256 = %s", ["A" * 64]),
            ("size = %s", [-1]),
        )
        for assignment, values in refused:
            with (
                self.subTest(assignment=assignment),
                self.assertRaises(IntegrityError),
                mute_logger("odoo.sql_db"),
                self.env.cr.savepoint(),
            ):
                self.env.cr.execute(
                    SQL("UPDATE medilab_laboratory_content SET %s WHERE id = %s", SQL(assignment, *values), content.id)
                )
