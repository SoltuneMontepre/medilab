from odoo.fields import Command
from odoo.tests import tagged

from .laboratory_api_case import LaboratoryApiCase
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    FOLDER_ARCHIVED,
    FOLDER_EXISTS,
    IDEMPOTENCY_CONFLICT,
    INVALID_REQUEST,
    NOT_FOUND,
    PERMISSION_DENIED,
)
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_DEVICE, MODEL_LABORATORY_FOLDER
from odoo.addons.sol_laboratory.constants.xml_ids import LABORATORY_FILES_GROUP


@tagged("post_install", "-at_install")
class TestLaboratoryApiFolders(LaboratoryApiCase):
    def setUp(self):
        super().setUp()
        self.key = self.signed_in_key(self.tester, "tester-installation")
        self.members_key = self.signed_in_key(self.member, "members-installation")
        self.outsiders_key = self.signed_in_key(self.outsider, "outsiders-installation")
        self.device = self.env[MODEL_LABORATORY_DEVICE].search([("client_uid", "=", "tester-installation")])

    def create_folder(self, name, key=None, idempotency_key=None):
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self.api("POST", "/folders", {"name": name}, key=key or self.key, headers=headers)

    def test_a_person_lists_the_folders_they_are_a_member_of_with_what_they_may_do(self):
        archived = self.env[MODEL_LABORATORY_FOLDER].create({"name": "Old runs", "owner_id": self.tester.id})
        archived.with_user(self.administrator).action_archive_folder()

        folders = {folder["name"]: folder for folder in self.api("GET", "/folders", key=self.key).json()["folders"]}
        members = self.api("GET", "/folders", key=self.members_key).json()["folders"]

        self.assertEqual(set(folders), {"HPLC", "Old runs"})
        self.assertEqual(
            {key: folders["HPLC"][key] for key in ("role", "status", "sync_mode", "can_share", "sample", "category")},
            {
                "role": "owner",
                "status": "in_use",
                "sync_mode": "upload_only",
                "can_share": True,
                "sample": None,
                "category": None,
            },
        )
        self.assertEqual((folders["Old runs"]["status"], folders["Old runs"]["can_share"]), ("archived", False))
        self.assertTrue(folders["Old runs"]["retention_until"])
        self.assertEqual(
            [(folder["name"], folder["role"], folder["can_share"]) for folder in members], [("HPLC", "member", False)]
        )
        self.assertEqual(self.api("GET", "/folders", key=self.outsiders_key).json()["folders"], [])

    def test_creating_a_folder_makes_the_person_its_owner_from_this_computer(self):
        folder = self.create_folder("AAS").json()["folder"]

        created = self.env[MODEL_LABORATORY_FOLDER].browse(folder["id"])
        self.assertEqual((folder["name"], folder["root"], folder["role"]), ("AAS", "AAS", "owner"))
        self.assertEqual((created.owner_id, created.created_by_device_id), (self.tester, self.device))

    def test_a_name_the_person_already_has_a_folder_of_is_refused_without_a_key(self):
        self.create_folder("AAS")

        self.assertApiRefused(FOLDER_EXISTS, self.create_folder("AAS"))
        self.assertApiRefused(FOLDER_EXISTS, self.create_folder("HPLC"))
        self.assertEqual(self.create_folder("AAS", key=self.members_key).status_code, 200)

    def test_a_creation_repeated_with_its_idempotency_key_answers_with_the_folder_it_created(self):
        first = self.create_folder("AAS", idempotency_key="create-aas-1")
        again = self.create_folder("AAS", idempotency_key="create-aas-1")

        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json(), first.json())
        self.assertEqual(self.env[MODEL_LABORATORY_FOLDER].search_count([("root", "=", "AAS")]), 1)

    def test_an_idempotency_key_sent_with_another_request_is_refused(self):
        self.create_folder("AAS", idempotency_key="create-1")

        self.assertApiRefused(IDEMPOTENCY_CONFLICT, self.create_folder("GC", idempotency_key="create-1"))
        self.assertApiRefused(INVALID_REQUEST, self.create_folder("GC", idempotency_key="a key with spaces"))

    def test_a_folder_is_named_never_given_a_path(self):
        for name in ("C:\\Users\\lab\\HPLC", "/home/lab/HPLC", "HPLC/run-01", "..", "~lab"):
            with self.subTest(name=name):
                self.assertApiRefused(INVALID_REQUEST, self.create_folder(name))
                folder = self.api("PATCH", f"/folders/{self.folder.id}", {"name": name}, key=self.key)
                self.assertApiRefused(INVALID_REQUEST, folder)
        self.assertEqual(self.folder.name, "HPLC")

    def test_a_person_without_the_laboratory_files_permission_gets_no_folder(self):
        self.tester.write({"group_ids": [Command.unlink(self.env.ref(LABORATORY_FILES_GROUP).id)]})

        for method, path in (("GET", "/folders"), ("GET", f"/folders/{self.folder.id}")):
            with self.subTest(path=path):
                self.assertApiRefused(PERMISSION_DENIED, self.api(method, path, key=self.key))
        self.assertApiRefused(PERMISSION_DENIED, self.create_folder("AAS"))

    def test_a_folder_the_person_is_not_a_member_of_is_not_found(self):
        for path in (f"/folders/{self.folder.id}", "/folders/0"):
            with self.subTest(path=path):
                self.assertApiRefused(NOT_FOUND, self.api("GET", path, key=self.outsiders_key))
        renamed = self.api("PATCH", f"/folders/{self.folder.id}", {"name": "Mine"}, key=self.outsiders_key)
        self.assertApiRefused(NOT_FOUND, renamed)

    def test_the_owner_renames_a_folder_and_its_root_stays(self):
        folder = self.api("PATCH", f"/folders/{self.folder.id}", {"name": "HPLC 2026"}, key=self.key).json()["folder"]

        self.assertEqual((folder["name"], folder["root"]), ("HPLC 2026", "HPLC"))
        self.assertEqual(
            self.api("GET", f"/folders/{self.folder.id}", key=self.members_key).json()["folder"]["name"], "HPLC 2026"
        )

    def test_a_member_who_does_not_own_the_folder_does_not_rename_it(self):
        renamed = self.api("PATCH", f"/folders/{self.folder.id}", {"name": "Mine"}, key=self.members_key)

        self.assertApiRefused(PERMISSION_DENIED, renamed)

    def test_a_turned_off_folder_is_still_renamed_and_an_archived_one_is_not(self):
        self.folder.with_user(self.administrator).action_turn_off()
        self.assertEqual(
            self.api("PATCH", f"/folders/{self.folder.id}", {"name": "Off"}, key=self.key).status_code, 200
        )

        self.folder.with_user(self.administrator).action_archive_folder()
        archived = self.api("PATCH", f"/folders/{self.folder.id}", {"name": "Archived"}, key=self.key)
        self.assertApiRefused(FOLDER_ARCHIVED, archived)
        self.assertEqual(
            self.api("GET", f"/folders/{self.folder.id}", key=self.key).json()["folder"]["status"], "archived"
        )
