import hashlib
import os
from unittest.mock import patch

from odoo.tests import tagged

from .laboratory_bucket_case import closed_port
from .laboratory_upload_case import LaboratoryUploadCase
from odoo.addons.sol_laboratory.constants.laboratory_bucket import ADDRESS_VARIABLE, PART_SIZE
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    CONFLICT,
    DUPLICATE,
    FAILED,
    IDEMPOTENCY_CONFLICT,
    INVALID_REQUEST,
    LOCKED,
    NOT_FOUND,
    SYNCED,
    VERIFIED,
)
from odoo.addons.sol_laboratory.constants.laboratory_uploads import (
    COMPLETED,
    PREPARED,
    SHA256_MISMATCH,
    STORAGE_UNAVAILABLE,
    UNCHANGED,
    UPLOAD_CLOSED,
    UPLOAD_CONFLICT,
    UPLOAD_FAILED,
    UPLOAD_INCOMPLETE,
    VERIFYING,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_CONTENT,
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FOLDER,
)
from odoo.addons.sol_laboratory.services import laboratory_bucket

RUN = b"mau,Pb\nLAB-26-0412,0.012\n"


@tagged("post_install", "-at_install")
class TestLaboratoryUploads(LaboratoryUploadCase):
    """Uploading laboratory files through the API, straight to the bucket, and storing their versions."""

    def file(self, path="HPLC/run-01.csv", folder=None):
        return self.env[MODEL_LABORATORY_FILE].search(
            [("folder_id", "=", (folder or self.folder).id), ("path", "=", path)]
        )

    def test_a_file_uploaded_in_parts_is_stored_with_the_person_the_computer_the_size_and_the_hash(self):
        data = os.urandom(PART_SIZE + 100)

        upload = self.upload(data)

        version = self.file().current_version_id
        device = self.env[MODEL_LABORATORY_DEVICE].search([("client_uid", "=", "hplc-installation")])
        self.assertEqual((upload["status"], upload["version"]["id"]), (COMPLETED, version.id))
        self.assertEqual(
            (version.number, version.source, version.user_id, version.device_id, version.size, version.sha256),
            (1, SYNCED, self.tester, device, len(data), hashlib.sha256(data).hexdigest()),
        )
        content = version.content_id.sudo()
        self.assertEqual(content.state, VERIFIED)
        self.assertEqual(self.read_back(content.object_key), (version.sha256, len(data)))

    def test_content_the_file_already_has_is_not_uploaded_and_the_current_version_stays(self):
        first = self.upload(RUN)
        contents = self.env[MODEL_LABORATORY_CONTENT].sudo().search_count([])

        response = self.prepare(RUN)

        upload = response.json()["upload"]
        self.assertEqual((upload["status"], upload["part_count"]), (UNCHANGED, 0))
        self.assertEqual(upload["version"]["id"], first["version"]["id"])
        self.assertEqual(self.env[MODEL_LABORATORY_CONTENT].sudo().search_count([]), contents)

    def test_content_stored_for_another_file_is_uploaded_then_shares_the_stored_bytes(self):
        self.upload(RUN)

        response = self.prepare(RUN, path="HPLC/run-01 (copy).csv")
        self.assertEqual((response.json()["upload"]["status"], response.json()["upload"]["part_count"]), (PREPARED, 1))
        upload = self.upload(RUN, path="HPLC/run-01 (copy).csv")

        original, copy = self.file().current_version_id, self.file("HPLC/run-01 (copy).csv").current_version_id
        self.assertEqual(upload["status"], COMPLETED)
        self.assertEqual(copy.content_id, original.content_id)
        duplicate = self.record(upload).content_id
        self.assertEqual(duplicate.state, DUPLICATE)
        self.env.cr.postcommit.run()
        self.assertIsNone(laboratory_bucket.object_size(duplicate.object_key))
        self.assertEqual(laboratory_bucket.object_size(original.content_id.sudo().object_key), len(RUN))

    def test_a_file_uploaded_from_version_10_while_11_is_current_is_a_conflict_and_11_stays(self):
        file = self.file_of("HPLC/run-01.csv")
        versions = [self.save(file, f"run 1, save {number}") for number in range(1, 12)]

        upload = self.upload(RUN, base_version=versions[9])

        self.assertEqual(upload["status"], UPLOAD_CONFLICT)
        self.assertEqual((upload["version"]["number"], upload["version"]["source"]), (12, CONFLICT))
        self.assertEqual(file.current_version_id, versions[10])

    def test_content_that_is_not_the_one_claimed_fails_with_no_version(self):
        response = self.prepare(RUN)
        upload = response.json()["upload"]
        self.put_parts(upload, b"x" * len(RUN))
        self.finalize(upload)

        self.run_jobs()

        read = self.read(upload)
        self.assertEqual(
            (read["status"], read["failure_code"], read["version"]), (UPLOAD_FAILED, SHA256_MISMATCH, None)
        )
        self.assertEqual(self.record(upload).content_id.state, FAILED)
        self.assertFalse(self.file())

    def test_finalizing_before_every_part_is_uploaded_is_refused_and_the_upload_stays_prepared(self):
        data = os.urandom(PART_SIZE + 10)
        upload = self.prepare(data).json()["upload"]
        response = self.api(
            "POST", f"/folders/{self.folder.id}/uploads/{upload['id']}/parts", {"part_numbers": [1]}, key=self.key
        )
        self.call_presigned("PUT", response.json()["parts"][0]["url"], data[:PART_SIZE])

        with self.expected_http_warnings("Upload every part before finalizing: 2 parts are expected."):
            self.assertApiRefused(UPLOAD_INCOMPLETE, self.finalize(upload))

        self.assertEqual(self.read(upload)["status"], PREPARED)

    def test_an_empty_file_is_uploaded_without_parts(self):
        upload = self.upload(b"", path="HPLC/empty.csv")

        self.assertEqual((upload["status"], upload["part_count"], upload["version"]["size"]), (COMPLETED, 0, 0))
        wrong = {"path": "HPLC/other.csv", "size": 0, "sha256": "0" * 64}
        with self.expected_http_warnings(
            "Empty content has the SHA-256 e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855."
        ):
            response = self.api(
                "POST", f"/folders/{self.folder.id}/uploads", wrong, key=self.key, headers={"Idempotency-Key": "empty-2"}
            )
        self.assertApiRefused(INVALID_REQUEST, response)

    def test_preparing_again_with_the_idempotency_key_answers_with_the_same_upload(self):
        first = self.prepare(RUN, idempotency_key="run-01-upload")
        again = self.prepare(RUN, idempotency_key="run-01-upload")
        with self.expected_http_warnings(
            "This Idempotency-Key was already sent with another request.",
            "This route needs the parameter Idempotency-Key.",
        ):
            other = self.prepare(b"another run", idempotency_key="run-01-upload")
            without = self.api(
                "POST",
                f"/folders/{self.folder.id}/uploads",
                {"path": "HPLC/run-01.csv", "size": len(RUN), "sha256": hashlib.sha256(RUN).hexdigest()},
                key=self.key,
            )

        self.assertEqual(again.json()["upload"]["id"], first.json()["upload"]["id"])
        self.assertApiRefused(IDEMPOTENCY_CONFLICT, other)
        self.assertApiRefused(INVALID_REQUEST, without)

    def test_finalizing_twice_stores_one_version(self):
        upload = self.prepare(RUN).json()["upload"]
        self.put_parts(upload, RUN)

        first, second = self.finalize(upload), self.finalize(upload)
        self.run_jobs()
        self.run_jobs()
        third = self.finalize(upload)

        self.assertEqual((first.json()["upload"]["status"], second.json()["upload"]["status"]), (VERIFYING, VERIFYING))
        self.assertEqual(third.json()["upload"]["status"], COMPLETED)
        self.assertEqual(len(self.file().version_ids), 1)

    def test_a_file_someone_else_locked_is_refused_before_any_byte_is_sent(self):
        file = self.file_of("HPLC/run-01.csv")
        self.save(file, "run 1")
        file.with_user(self.member)._lock()
        contents = self.env[MODEL_LABORATORY_CONTENT].sudo()
        last_id = contents.search([], order="id desc", limit=1).id or 0

        locked_warning = self.timestamped_http_warning(
            "lab.member (base.group_user,sol_laboratory.group_permission_laboratory_folder_create_all) "
            "has locked HPLC/run-01.csv until "
        )
        with self.expected_http_warnings(locked_warning):
            response = self.prepare(RUN)

        self.assertApiRefused(LOCKED, response)
        self.assertFalse(contents.search([("id", ">", last_id)]))

    def test_a_lock_taken_before_finalizing_refuses_finalizing_and_the_upload_stays_prepared(self):
        upload = self.prepare(RUN).json()["upload"]
        self.put_parts(upload, RUN)
        file = self.file_of("HPLC/run-01.csv")
        self.save(file, "run 1")
        file.with_user(self.member)._lock()

        locked_warning = self.timestamped_http_warning(
            "lab.member (base.group_user,sol_laboratory.group_permission_laboratory_folder_create_all) "
            "has locked HPLC/run-01.csv until "
        )
        with self.expected_http_warnings(locked_warning):
            self.assertApiRefused(LOCKED, self.finalize(upload))

        self.assertEqual(self.read(upload)["status"], PREPARED)

    def test_another_computers_upload_is_not_found(self):
        upload = self.prepare(RUN).json()["upload"]
        other = self.signed_in_key(self.member, "member-installation")
        another_folder = self.env[MODEL_LABORATORY_FOLDER].create({"name": "AAS", "owner_id": self.tester.id})

        warning = "This upload does not exist or you do not have access to it."
        with self.expected_http_warnings(warning, warning):
            for key, folder_id in ((other, self.folder.id), (self.key, another_folder.id)):
                with self.subTest(folder_id=folder_id):
                    response = self.api("GET", f"/folders/{folder_id}/uploads/{upload['id']}", key=key)
                    self.assertApiRefused(NOT_FOUND, response)

    def test_part_addresses_are_for_the_parts_of_a_prepared_upload_only(self):
        upload = self.prepare(RUN).json()["upload"]
        path = f"/folders/{self.folder.id}/uploads/{upload['id']}/parts"

        with self.expected_http_warnings("Ask for at most 100 parts, numbered from 1 to 1."):
            refused = self.api("POST", path, {"part_numbers": [2]}, key=self.key)
        given = self.api("POST", path, {"part_numbers": [1]}, key=self.key)
        self.put_parts(upload, RUN)
        self.finalize(upload)
        with self.expected_http_warnings("This upload is closed; prepare the file again."):
            closed = self.api("POST", path, {"part_numbers": [1]}, key=self.key)

        self.assertApiRefused(INVALID_REQUEST, refused)
        self.assertEqual([part["number"] for part in given.json()["parts"]], [1])
        self.assertLessEqual(given.json()["expires_at"], upload["expires_at"])
        self.assertApiRefused(UPLOAD_CLOSED, closed)

    def test_a_part_address_writes_nothing_once_the_upload_is_completed(self):
        upload = self.prepare(RUN).json()["upload"]
        response = self.api(
            "POST", f"/folders/{self.folder.id}/uploads/{upload['id']}/parts", {"part_numbers": [1]}, key=self.key
        )
        url = response.json()["parts"][0]["url"]
        self.call_presigned("PUT", url, RUN)
        self.finalize(upload)
        self.run_jobs()

        self.assertEqual(self.call_presigned("PUT", url, b"another run").status_code, 404)
        content = self.file().current_version_id.content_id.sudo()
        self.assertEqual(self.read_back(content.object_key), (hashlib.sha256(RUN).hexdigest(), len(RUN)))

    def test_while_the_bucket_cannot_be_reached_preparing_is_answered_storage_unavailable(self):
        with patch.dict(os.environ, {ADDRESS_VARIABLE: f"http://127.0.0.1:{closed_port()}"}), self.expected_http_warnings(
            "The laboratory files bucket cannot be reached; try again shortly."
        ):
            response = self.prepare(RUN)

        self.assertApiRefused(STORAGE_UNAVAILABLE, response)
        self.assertIn("Retry-After", response.headers)

    def test_a_known_sha256_gives_no_access_to_content_stored_for_another_folder(self):
        self.upload(RUN)
        stored = self.file().current_version_id.content_id.sudo()
        other_folder = self.folder.create({"name": "AAS", "owner_id": self.outsider.id})
        outsider = self.signed_in_key(self.outsider, "aas-installation")

        prepared = self.prepare(RUN, key=outsider, folder=other_folder)
        garbage = prepared.json()["upload"]
        self.put_parts(garbage, b"x" * len(RUN), key=outsider, folder=other_folder)
        self.finalize(garbage, key=outsider, folder=other_folder)
        self.run_jobs()
        refused = self.read(garbage, key=outsider, folder=other_folder)
        honest = self.upload(RUN, path="run-01.csv", key=outsider, folder=other_folder)
        with self.expected_http_warnings("This upload does not exist or you do not have access to it."):
            theirs = self.api("GET", f"/folders/{self.folder.id}/uploads/{garbage['id']}", key=outsider)

        self.assertEqual((prepared.json()["upload"]["status"], garbage["part_count"]), (PREPARED, 1))
        self.assertEqual((refused["status"], refused["failure_code"]), (UPLOAD_FAILED, SHA256_MISMATCH))
        self.assertEqual(honest["status"], COMPLETED)
        self.assertEqual(self.file("run-01.csv", other_folder).current_version_id.content_id, stored)
        for answer in (prepared.text, str(refused), str(honest)):
            self.assertNotIn(stored.object_key, answer)
        self.assertApiRefused(NOT_FOUND, theirs)
