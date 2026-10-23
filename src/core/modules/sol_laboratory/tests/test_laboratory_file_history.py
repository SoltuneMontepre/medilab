import hashlib
import urllib.parse
import uuid
from datetime import datetime, timedelta

from odoo import fields
from odoo.tests import tagged

from .audit_case import AuditLookup
from .laboratory_api_case import LaboratoryApiCase
from .laboratory_bucket_case import LaboratoryBucketTools, remove_written_objects
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    FOLDER_ARCHIVED,
    IDEMPOTENCY_CONFLICT,
    LOCKED,
    NOT_FOUND,
    RESTORED,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_CONTENT
from odoo.addons.sol_laboratory.constants.settings import DEFAULT_LABORATORY_FILE_URL_MINUTES
from odoo.addons.sol_laboratory.services import laboratory_bucket
from odoo.addons.sol_laboratory.services.laboratory_file_error import LaboratoryFileError


@tagged("post_install", "-at_install")
class TestLaboratoryFileHistory(AuditLookup, LaboratoryBucketTools, LaboratoryApiCase):
    """A computer reading a folder's files and a file's history, downloading versions straight from the bucket and
    restoring one, through the laboratory files API, and a person downloading a version in the back office."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.auditor = cls.new_auditor()

    def setUp(self):
        super().setUp()
        remove_written_objects(self)
        self.key = self.signed_in_key(self.tester, "hplc-installation")
        self.file = self.file_of("HPLC/run-01.csv")

    def save_with_bytes(self, file, text):
        """Save the text as a version of the file, with its bytes in the bucket, as an upload stores it."""
        data = text.encode()
        content = self.env[MODEL_LABORATORY_CONTENT].sudo()._new_pending()
        laboratory_bucket.write(content.object_key, iter([data]))
        settled = content._settle(hashlib.sha256(data).hexdigest(), len(data))
        return file._add_version(content=settled, source="synced", user=self.tester)

    def versions_path(self, file=None, folder=None):
        return f"/folders/{(folder or self.folder).id}/files/{(file or self.file).id}/versions"

    def restore(self, version, key=None, idempotency_key=None):
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self.api("POST", f"{self.versions_path()}/{version.id}/restore", key=key or self.key, headers=headers)

    def test_a_folder_lists_its_files_with_their_current_versions_and_locks_page_by_page(self):
        files = [self.file_of(f"HPLC/run-{number:02}.csv") for number in range(1, 4)]
        for file in files:
            self.save(file, f"{file.path}, bản 1")
        files[1].with_user(self.member)._lock()
        path = f"/folders/{self.folder.id}/files"

        first = self.api("GET", f"{path}?limit=2", key=self.key).json()
        rest = self.api("GET", f"{path}?after={first['next_after']}&limit=2", key=self.key).json()

        self.assertEqual([entry["path"] for entry in first["files"] + rest["files"]], [file.path for file in files])
        self.assertEqual(first["next_after"], files[1].id)
        self.assertIsNone(rest["next_after"])
        listed = {entry["path"]: entry for entry in first["files"]}
        self.assertEqual(listed[files[0].path]["current_version"]["number"], 1)
        self.assertEqual(listed[files[1].path]["lock"]["user"]["id"], self.member.id)
        self.assertIsNone(listed[files[0].path]["lock"])

    def test_a_listing_shows_another_members_lock_without_their_computer(self):
        self.save(self.file, "run 1")
        members_key = self.signed_in_key(self.member, "members-installation")
        locked = self.api("POST", f"/folders/{self.folder.id}/files/{self.file.id}/lock", key=members_key).json()
        self.assertIsNotNone(locked["lock"]["device_id"])

        listed = self.api("GET", f"/folders/{self.folder.id}/files", key=self.key).json()["files"]

        self.assertEqual(
            listed[0]["lock"],
            {"user": {"id": self.member.id, "name": self.member.name}, "expires_at": locked["lock"]["expires_at"]},
        )

    def test_a_file_gives_every_version_newest_first(self):
        versions = [self.save(self.file, f"run 1, bản {number}") for number in range(1, 4)]

        response = self.api("GET", self.versions_path(), key=self.key)

        self.assertEqual([version["id"] for version in response.json()["versions"]], [v.id for v in reversed(versions)])

    def test_files_of_a_folder_the_person_is_not_a_member_of_are_not_found(self):
        self.save(self.file, "run 1")
        outsider = self.signed_in_key(self.outsider, "aas-installation")

        warning = "This laboratory folder does not exist or you do not have access to it."
        with self.expected_http_warnings(warning, warning, warning):
            for path in (f"/folders/{self.folder.id}/files", self.versions_path(), f"/folders/{self.folder.id}/changes"):
                with self.subTest(path=path):
                    self.assertApiRefused(NOT_FOUND, self.api("GET", path, key=outsider))

    def test_a_version_is_downloaded_straight_from_the_bucket_for_reading_only_and_the_download_is_audited(self):
        first = self.save_with_bytes(self.file, "mau,Pb\nLAB-26-0412,0.012")
        self.save_with_bytes(self.file, "mau,Pb\nLAB-26-0412,0.013")

        response = self.api("POST", f"{self.versions_path()}/{first.id}/download", key=self.key)

        answer = response.json()
        read = self.call_presigned("GET", answer["url"])
        self.assertEqual(read.content, b"mau,Pb\nLAB-26-0412,0.012")
        self.assertIn(urllib.parse.quote("run-01.csv"), read.headers["Content-Disposition"])
        self.assertEqual(self.call_presigned("PUT", answer["url"], b"other").status_code, 403)
        expires_at = datetime.strptime(answer["expires_at"][:19], "%Y-%m-%dT%H:%M:%S")
        expected = fields.Datetime.now() + timedelta(minutes=DEFAULT_LABORATORY_FILE_URL_MINUTES)
        self.assertAlmostEqual(expires_at, expected, delta=timedelta(minutes=1))
        entry = self.entries(self.file, "download")
        self.assertEqual((entry.user_id, entry.note), (self.tester, "Version 1"))

    def test_a_version_of_another_file_or_folder_is_not_found(self):
        version = self.save(self.file, "run 1")
        other = self.file_of("HPLC/run-02.csv")
        self.save(other, "run 2")
        folder = self.folder.create({"name": "AAS", "owner_id": self.tester.id})

        with self.expected_http_warnings(
            "This version is not a version of the file.",
            "This file does not exist in the folder.",
        ):
            for path in (
                f"{self.versions_path(other)}/{version.id}/download",
                f"{self.versions_path(folder=folder)}/{version.id}/download",
            ):
                with self.subTest(path=path):
                    self.assertApiRefused(NOT_FOUND, self.api("POST", path, key=self.key))
        self.assertFalse(self.entries(self.file, "download"))

    def test_restoring_version_3_of_5_adds_version_6_with_its_content(self):
        versions = [self.save(self.file, f"run 1, bản {number}") for number in range(1, 6)]

        response = self.restore(versions[2])

        restored = response.json()["version"]
        self.assertEqual(
            (restored["number"], restored["source"], restored["restored_from_id"]), (6, RESTORED, versions[2].id)
        )
        version = self.file.current_version_id
        self.assertEqual((version.number, version.content_id), (6, versions[2].content_id))
        self.assertEqual(restored["device"]["name"], "HPLC-PC")

    def test_a_restore_repeated_with_its_idempotency_key_adds_one_version(self):
        first, second = self.save(self.file, "run 1"), self.save(self.file, "run 2")

        once, again = self.restore(first, idempotency_key="restore-1"), self.restore(first, idempotency_key="restore-1")
        with self.expected_http_warnings("This Idempotency-Key was already sent with another request."):
            other = self.restore(second, idempotency_key="restore-1")
        without = [self.restore(first) for _ in range(2)]

        self.assertEqual(once.json()["version"]["id"], again.json()["version"]["id"])
        self.assertApiRefused(IDEMPOTENCY_CONFLICT, other)
        self.assertEqual([response.json()["version"]["number"] for response in without], [4, 5])

    def test_a_restore_is_refused_while_someone_else_locks_the_file_or_the_folder_is_archived(self):
        first = self.save(self.file, "run 1")
        self.save(self.file, "run 2")
        self.file.with_user(self.member)._lock()

        locked_warning = self.timestamped_http_warning(
            "lab.member (base.group_user,sol_laboratory.group_permission_laboratory_folder_create_all) "
            "has locked HPLC/run-01.csv until "
        )
        with self.expected_http_warnings(locked_warning):
            self.assertApiRefused(LOCKED, self.restore(first, idempotency_key=uuid.uuid4().hex))
        self.file.with_user(self.member)._unlock()
        self.folder.with_user(self.administrator).action_archive_folder()
        with self.expected_http_warnings("This laboratory folder is archived: it is read, not changed."):
            self.assertApiRefused(FOLDER_ARCHIVED, self.restore(first))
        self.assertEqual(len(self.file.version_ids), 2)

    def test_a_member_downloads_a_version_in_the_back_office_and_nobody_else_does(self):
        version = self.save_with_bytes(self.file, "run 1")

        action = version.with_user(self.member).action_download()

        self.assertEqual((action["type"], action["target"]), ("ir.actions.act_url", "new"))
        self.assertEqual(self.call_presigned("GET", action["url"]).content, b"run 1")
        # Recorded when the address is issued, as the browser then reads the bucket without Odoo.
        entry = self.entries(self.file, "download")
        self.assertEqual((len(entry), entry.user_id, entry.note), (1, self.member, "Version 1"))
        with self.assertRaises(LaboratoryFileError):
            version.with_user(self.administrator).action_download()
        self.assertEqual(self.entries(self.file, "download"), entry)
