from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import tagged

from .laboratory_files_case import LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    FOLDER_ADMINISTER,
    FOLDER_ARCHIVED,
    FOLDER_DISABLED,
    FOLDER_READ,
    FOLDER_SHARE,
    FOLDER_WRITE,
    LOCKED,
    NOT_ELIGIBLE,
    NOT_FOUND,
    PERMISSION_DENIED,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_FOLDER,
    MODEL_LABORATORY_FOLDER_MEMBER,
    MODEL_LABORATORY_SYNC_RULE,
)
from odoo.addons.sol_laboratory.constants.xml_ids import LABORATORY_FILES_GROUP
from odoo.addons.sol_laboratory.services.record_id import persisted_id


@tagged("post_install", "-at_install")
class TestLaboratoryFolderAccess(LaboratoryFilesCase):
    def test_members_read_their_folders_and_nobody_else_sees_them(self):
        folders = self.env[MODEL_LABORATORY_FOLDER]

        for user in (self.tester, self.member):
            with self.subTest(user=user.login):
                self.assertEqual(folders.with_user(user).search([]), self.folder)
        self.assertFalse(folders.with_user(self.outsider).search([]))
        with self.assertRaises(AccessError):
            self.folder.with_user(self.outsider).read(["name"])
        with self.assertRaises(AccessError):
            folders.with_user(self.colleague).search([])

    def test_members_read_the_members_and_rules_of_their_folders(self):
        rule = self.env[MODEL_LABORATORY_SYNC_RULE].create(
            {"folder_id": self.folder.id, "kind": "extension", "pattern": "csv"}
        )
        members = self.env[MODEL_LABORATORY_FOLDER_MEMBER]

        self.assertEqual(members.with_user(self.member).search([]).user_id, self.tester | self.member)
        self.assertEqual(rule.with_user(self.member).pattern, "csv")
        self.assertFalse(members.with_user(self.outsider).search([]))
        self.assertFalse(self.env[MODEL_LABORATORY_SYNC_RULE].with_user(self.outsider).search([]))

    def test_people_read_only_their_own_computers(self):
        devices = self.env[MODEL_LABORATORY_DEVICE]
        values = {"name": "HPLC-PC", "platform": "windows"}
        own = devices.create({**values, "user_id": self.tester.id, "client_uid": "tester-installation"})
        devices.create({**values, "user_id": self.member.id, "client_uid": "member-installation"})

        self.assertEqual(devices.with_user(self.tester).search([]), own)

    def test_members_read_and_write_their_folder(self):
        for user in (self.tester, self.member):
            for access in (FOLDER_READ, FOLDER_WRITE):
                with self.subTest(user=user.login, access=access):
                    self.folder.with_user(user)._check_folder_access(access)

    def test_a_person_who_is_not_a_member_gets_nothing_from_the_folder(self):
        for user in (self.outsider, self.administrator):
            for access in (FOLDER_READ, FOLDER_WRITE):
                with self.subTest(user=user.login, access=access):
                    self.assertRefused(NOT_FOUND, self.folder.with_user(user)._check_folder_access, access)
        self.assertRefused(NOT_FOUND, self.folder.with_user(self.outsider)._check_folder_access, FOLDER_SHARE)

    def test_losing_the_permission_stops_a_member_and_keeps_the_membership(self):
        self.member.group_ids = [Command.unlink(persisted_id(self.env.ref(LABORATORY_FILES_GROUP)))]

        self.assertRefused(PERMISSION_DENIED, self.folder.with_user(self.member)._check_folder_access, FOLDER_READ)
        self.assertIn(self.member, self.folder.member_ids.user_id)

    def test_a_turned_off_folder_is_read_but_its_files_are_not_written(self):
        self.folder.enabled = False

        self.folder.with_user(self.member)._check_folder_access(FOLDER_READ)
        self.assertRefused(FOLDER_DISABLED, self.folder.with_user(self.member)._check_folder_access, FOLDER_WRITE)

    def test_an_archived_folder_is_read_but_its_files_are_not_written(self):
        self.folder.archived_at = "2026-10-20 08:00:00"

        self.folder.with_user(self.member)._check_folder_access(FOLDER_READ)
        self.assertRefused(FOLDER_ARCHIVED, self.folder.with_user(self.member)._check_folder_access, FOLDER_WRITE)

    def test_only_the_owner_and_administrators_share_a_folder(self):
        self.folder.with_user(self.tester)._check_folder_access(FOLDER_SHARE)
        self.folder.with_user(self.administrator)._check_folder_access(FOLDER_SHARE)
        self.assertRefused(PERMISSION_DENIED, self.folder.with_user(self.member)._check_folder_access, FOLDER_SHARE)

    def test_only_administrators_administer_a_folder(self):
        self.folder.with_user(self.administrator)._check_folder_access(FOLDER_ADMINISTER)
        self.assertRefused(
            PERMISSION_DENIED, self.folder.with_user(self.tester)._check_folder_access, FOLDER_ADMINISTER
        )

    def test_a_folder_someone_else_is_editing_is_not_shared_meanwhile(self):
        self.folder.with_user(self.administrator).lock_take()

        self.assertRefused(LOCKED, self.folder.with_user(self.tester)._check_folder_access, FOLDER_SHARE)

    def test_only_people_with_the_permission_can_be_added_to_a_folder(self):
        self.outsider.active = False
        members = self.env[MODEL_LABORATORY_FOLDER_MEMBER]

        for user in (self.colleague, self.outsider):
            with self.subTest(user=user.login):
                self.assertRefused(NOT_ELIGIBLE, members.create, {"folder_id": self.folder.id, "user_id": user.id})
