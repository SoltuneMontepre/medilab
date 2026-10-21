import base64
import hashlib
import os
import re
import time
import urllib.parse
from unittest.mock import patch

import requests
from botocore.exceptions import ClientError

from odoo.tests import tagged
from odoo.tools import mute_logger

from .laboratory_bucket_case import LaboratoryBucketCase, closed_port
from odoo.addons.sol_laboratory.constants.laboratory_bucket import ACCESS_KEY_VARIABLE, ADDRESS_VARIABLE, PART_SIZE
from odoo.addons.sol_laboratory.services import laboratory_bucket

# The bucket the setup of local development and CI makes without access for Odoo's key (garage-setup in
# tools/infrastructure/docker-compose.yml).
OTHER_BUCKET = "laboratory-files-other"
MINUTE = 60


def in_chunks(data, size=1024 * 1024):
    for start in range(0, len(data), size):
        yield data[start : start + size]


@tagged("post_install", "-at_install")
class TestLaboratoryBucket(LaboratoryBucketCase):
    """The calls Odoo makes to the laboratory files bucket, against the bucket of local development and CI."""

    def upload_parts(self, key, upload_id, parts):
        for number, data in enumerate(parts, start=1):
            url = laboratory_bucket.part_address(key, upload_id, number, MINUTE)
            response = self.call_presigned("PUT", url, data)
            self.assertEqual(response.status_code, 200, response.text)

    def test_object_keys_are_random_and_tell_nothing_about_the_content(self):
        keys = {laboratory_bucket.new_object_key() for _ in range(100)}

        self.assertEqual(len(keys), 100)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{32}", key) for key in keys))

    def test_a_computer_uploads_parts_and_the_server_completes_the_upload_once(self):
        key = self.new_key()
        upload_id = self.new_upload(key)
        first, last = os.urandom(PART_SIZE), os.urandom(1000)

        self.upload_parts(key, upload_id, [first, last])
        parts = laboratory_bucket.uploaded_parts(key, upload_id)
        size = laboratory_bucket.complete_upload(key, upload_id, [(number, etag) for number, _size, etag in parts])
        again = laboratory_bucket.complete_upload(key, upload_id, [(number, etag) for number, _size, etag in parts])

        self.assertEqual([(number, part_size) for number, part_size, _etag in parts], [(1, PART_SIZE), (2, 1000)])
        self.assertEqual((size, again), (PART_SIZE + 1000, PART_SIZE + 1000))
        self.assertEqual(self.stored(key), (hashlib.sha256(first + last).hexdigest(), PART_SIZE + 1000))

    def test_a_part_address_writes_nothing_once_its_upload_is_completed(self):
        key = self.new_key()
        upload_id = self.new_upload(key)
        url = laboratory_bucket.part_address(key, upload_id, 1, MINUTE)
        self.call_presigned("PUT", url, b"the content")
        [(number, _size, etag)] = laboratory_bucket.uploaded_parts(key, upload_id)
        laboratory_bucket.complete_upload(key, upload_id, [(number, etag)])

        response = self.call_presigned("PUT", url, b"another content")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.stored(key), (hashlib.sha256(b"the content").hexdigest(), 11))

    def test_an_aborted_upload_is_gone_and_aborting_it_again_changes_nothing(self):
        key = self.new_key()
        upload_id = self.new_upload(key)
        self.upload_parts(key, upload_id, [b"a part"])

        laboratory_bucket.abort_upload(key, upload_id)
        laboratory_bucket.abort_upload(key, upload_id)

        with self.assertRaises(laboratory_bucket.UploadNotFound):
            laboratory_bucket.uploaded_parts(key, upload_id)
        with self.assertRaises(laboratory_bucket.UploadNotFound):
            laboratory_bucket.complete_upload(key, upload_id, [(1, '"etag"')])
        self.assertIsNone(laboratory_bucket.object_size(key))

    def test_odoo_writes_content_in_parts_and_returns_its_size_and_sha256(self):
        key = self.new_key()
        data = os.urandom(PART_SIZE + PART_SIZE // 2)

        size, sha256 = laboratory_bucket.write(key, in_chunks(data))

        self.assertEqual((size, sha256), (len(data), hashlib.sha256(data).hexdigest()))
        self.assertEqual(self.stored(key), (sha256, size))
        self.assertEqual(laboratory_bucket.object_size(key), size)

    def test_empty_content_is_written_and_read_back(self):
        key = self.new_key()

        size, sha256 = laboratory_bucket.write(key, iter(()))

        self.assertEqual((size, sha256), (0, hashlib.sha256(b"").hexdigest()))
        self.assertEqual(laboratory_bucket.object_size(key), 0)
        self.assertEqual(self.stored(key), (sha256, 0))

    def test_the_bucket_refuses_a_part_whose_sha256_is_not_its_content(self):
        bucket, client = laboratory_bucket._calls()
        key = self.new_key()
        upload_id = client.create_multipart_upload(Bucket=bucket.name, Key=key, ChecksumAlgorithm="SHA256")["UploadId"]
        self.addCleanup(laboratory_bucket.abort_upload, key, upload_id)
        wrong = base64.b64encode(hashlib.sha256(b"other content").digest()).decode()

        with self.assertRaises(ClientError) as caught:
            client.upload_part(
                Bucket=bucket.name, Key=key, UploadId=upload_id, PartNumber=1, Body=b"content", ChecksumSHA256=wrong
            )

        self.assertEqual(caught.exception.response["Error"]["Code"], "InvalidDigest")

    def test_a_write_that_fails_midway_leaves_no_upload(self):
        bucket, client = laboratory_bucket._calls()
        key = self.new_key()

        def failing():
            yield os.urandom(PART_SIZE)
            raise ConnectionError("The editing service stopped sending the document.")

        with self.assertRaises(ConnectionError):
            laboratory_bucket.write(key, failing())

        uploads = client.list_multipart_uploads(Bucket=bucket.name, Prefix=key).get("Uploads", [])
        self.assertEqual(uploads, [])
        self.assertIsNone(laboratory_bucket.object_size(key))

    def test_a_read_address_reads_the_object_under_its_file_name_and_writes_nothing(self):
        key = self.new_key()
        laboratory_bucket.write(key, iter([b"Pb: 0,004 mg/L"]))
        url = laboratory_bucket.read_address(key, MINUTE, "Kết quả HPLC.xlsx")

        read = self.call_presigned("GET", url)
        written = self.call_presigned("PUT", url, b"another content")

        self.assertEqual((read.status_code, read.content), (200, b"Pb: 0,004 mg/L"))
        self.assertIn(urllib.parse.quote("Kết quả HPLC.xlsx"), read.headers["Content-Disposition"])
        self.assertEqual(written.status_code, 403)
        self.assertEqual(self.stored(key)[1], 14)

    def test_a_read_address_stops_working_once_it_expires(self):
        key = self.new_key()
        laboratory_bucket.write(key, iter([b"content"]))
        url = laboratory_bucket.read_address(key, 1, "run-01.csv")

        time.sleep(2)
        response = self.call_presigned("GET", url)

        # Garage refuses an expired address with 400, S3 with 403.
        self.assertIn(response.status_code, (400, 403))
        self.assertNotEqual(response.content, b"content")

    def test_deleting_an_object_twice_changes_nothing(self):
        key = self.new_key()
        laboratory_bucket.write(key, iter([b"content"]))

        laboratory_bucket.delete(key)
        laboratory_bucket.delete(key)

        self.assertIsNone(laboratory_bucket.object_size(key))

    def test_odoos_key_reaches_its_own_bucket_only(self):
        bucket, client = laboratory_bucket._calls()

        for name, call in (
            ("write", lambda: client.put_object(Bucket=OTHER_BUCKET, Key="x", Body=b"x")),
            ("list", lambda: client.list_objects_v2(Bucket=OTHER_BUCKET)),
            ("create", lambda: client.create_bucket(Bucket=f"{bucket.name}-made-by-odoo")),
        ):
            with self.subTest(name=name), self.assertRaises(ClientError) as caught:
                call()
            self.assertEqual(caught.exception.response["ResponseMetadata"]["HTTPStatusCode"], 403)

    def test_an_object_is_not_read_without_a_presigned_address(self):
        key = self.new_key()
        laboratory_bucket.write(key, iter([b"content"]))
        bucket = self.bucket()

        response = requests.get(f"{bucket.address}/{bucket.name}/{key}", timeout=MINUTE)

        self.assertEqual(response.status_code, 403)

    def test_the_bucket_aborts_incomplete_uploads_after_seven_days(self):
        bucket, client = laboratory_bucket._calls()

        rules = client.get_bucket_lifecycle_configuration(Bucket=bucket.name)["Rules"]

        aborts = [
            rule["AbortIncompleteMultipartUpload"]["DaysAfterInitiation"]
            for rule in rules
            if rule["Status"] == "Enabled"
        ]
        self.assertEqual(aborts, [7])
        self.assertFalse([rule for rule in rules if rule.get("Expiration")])

    def test_a_bucket_that_does_not_answer_or_is_not_configured_is_unavailable(self):
        key = laboratory_bucket.new_object_key()
        down = {ADDRESS_VARIABLE: f"http://127.0.0.1:{closed_port()}"}
        for environment, cleared in ((down, ()), ({}, (ACCESS_KEY_VARIABLE,))):
            with (
                self.subTest(environment=environment, cleared=cleared),
                patch.dict(os.environ, environment),
                mute_logger("odoo.addons.sol_laboratory.services.laboratory_bucket"),
            ):
                for variable in cleared:
                    os.environ.pop(variable)

                with self.assertRaises(laboratory_bucket.BucketUnavailable):
                    laboratory_bucket.create_upload(key)
                self.assertFalse(laboratory_bucket.is_ready())

    def test_the_bucket_is_ready(self):
        self.assertTrue(laboratory_bucket.is_ready())
