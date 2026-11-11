from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .laboratory_files_case import LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.laboratory_files import (
    FOLDER_ARCHIVED,
    FOLDER_DISABLED,
    FOLDER_READ,
    FOLDER_SHARE,
    FOLDER_WRITE,
    NOT_FOUND,
    PERMISSION_DENIED,
)
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FOLDER,
    MODEL_LABORATORY_FOLDER_MEMBER,
    MODEL_LABORATORY_SYNC_RULE,
    MODEL_RES_CONFIG_SETTINGS,
)
from odoo.addons.sol_laboratory.constants.settings import LABORATORY_FOLDER_RETENTION_PARAMETER


@tagged("post_install", "-at_install")
class TestLaboratoryFolderAdministration(LaboratoryFilesCase):
    def test_administrators_turn_a_folder_off_and_on(self):
        folder = self.folder.with_user(self.administrator)

        folder.action_turn_off()
        self.assertFalse(self.folder.enabled)
        folder.action_turn_on()
        self.assertTrue(self.folder.enabled)
        self.assertRefused(PERMISSION_DENIED, self.folder.with_user(self.tester).action_turn_off)

    def test_a_turned_off_folder_refuses_its_files_and_is_still_renamed_and_shared(self):
        self.folder.with_user(self.administrator).action_turn_off()
        folder = self.folder.with_user(self.tester)

        folder._check_folder_access(FOLDER_READ)
        self.assertRefused(FOLDER_DISABLED, folder._check_folder_access, FOLDER_WRITE)
        folder._check_folder_access(FOLDER_SHARE)
        self.folder.name = "HPLC 2026"
        self.env[MODEL_LABORATORY_SYNC_RULE].create({"folder_id": self.folder.id, "kind": "prefix", "pattern": "run-"})
        self.env[MODEL_LABORATORY_FOLDER_MEMBER].create({"folder_id": self.folder.id, "user_id": self.outsider.id})
        self.assertIn(self.outsider, self.folder.member_ids.user_id)

    def test_archiving_sets_the_retention_date_from_the_retention_period(self):
        today = fields.Date.context_today(self.folder)
        other = self.env[MODEL_LABORATORY_FOLDER].create({"name": "AAS", "owner_id": self.tester.id})

        self.folder.with_user(self.administrator).action_archive_folder()
        self.env["ir.config_parameter"].set_str(LABORATORY_FOLDER_RETENTION_PARAMETER, "30")
        other.with_user(self.administrator).action_archive_folder()

        self.assertTrue(self.folder.archived_at)
        self.assertEqual(self.folder.retention_until, today + timedelta(days=1825))
        self.assertEqual(other.retention_until, today + timedelta(days=30))

    def test_only_administrators_archive_a_folder(self):
        self.assertRefused(PERMISSION_DENIED, self.folder.with_user(self.tester).action_archive_folder)
        self.assertFalse(self.folder.archived_at)

    def test_an_archived_folder_is_only_read_by_its_owner_and_members(self):
        self.folder.with_user(self.administrator).action_archive_folder()
        rule_values = {"folder_id": self.folder.id, "kind": "prefix", "pattern": "run-"}
        member_values = {"folder_id": self.folder.id, "user_id": self.outsider.id}

        for user in (self.tester, self.member):
            with self.subTest(user=user.login):
                self.folder.with_user(user)._check_folder_access(FOLDER_READ)
                self.assertRefused(FOLDER_ARCHIVED, self.folder.with_user(user)._check_folder_access, FOLDER_WRITE)
        self.assertRefused(FOLDER_ARCHIVED, self.folder.with_user(self.tester)._check_folder_access, FOLDER_SHARE)
        self.assertRefused(FOLDER_ARCHIVED, self.folder.write, {"name": "HPLC 2026"})
        self.assertRefused(FOLDER_ARCHIVED, self.env[MODEL_LABORATORY_SYNC_RULE].create, rule_values)
        self.assertRefused(FOLDER_ARCHIVED, self.env[MODEL_LABORATORY_FOLDER_MEMBER].create, member_values)

    def test_an_archived_folder_stays_archived_and_keeps_its_owner_and_state(self):
        folder = self.folder.with_user(self.administrator)
        folder.action_archive_folder()

        for action in (folder.action_archive_folder, folder.action_turn_off, folder.action_turn_on):
            with self.subTest(action=action.__name__):
                self.assertRefused(FOLDER_ARCHIVED, action)
        self.assertRefused(FOLDER_ARCHIVED, folder.write, {"owner_id": self.member.id})
        self.assertRefused(FOLDER_ARCHIVED, folder._check_folder_access, FOLDER_SHARE)

    def test_administrators_still_remove_the_members_of_an_archived_folder(self):
        self.folder.with_user(self.administrator).action_archive_folder()
        row = self.folder.member_ids.filtered(lambda member: member.user_id == self.member)

        row.with_user(self.administrator).unlink()

        self.assertNotIn(self.member, self.folder.member_ids.user_id)
        self.assertRefused(NOT_FOUND, self.folder.with_user(self.member)._check_folder_access, FOLDER_READ)

    def test_the_rules_of_an_archived_folder_stay(self):
        rule = self.env[MODEL_LABORATORY_SYNC_RULE].create(
            {"folder_id": self.folder.id, "kind": "extension", "pattern": "csv"}
        )
        self.folder.with_user(self.administrator).action_archive_folder()

        self.assertRefused(FOLDER_ARCHIVED, rule.write, {"enabled": False})
        self.assertRefused(FOLDER_ARCHIVED, rule.unlink)

    def test_the_retention_period_is_at_least_a_day(self):
        with self.assertRaises(ValidationError):
            self.env[MODEL_RES_CONFIG_SETTINGS].create({"laboratory_folder_retention_days": 0})
