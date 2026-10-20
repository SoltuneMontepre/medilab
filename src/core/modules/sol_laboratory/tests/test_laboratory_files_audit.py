from odoo.tests import tagged

from .audit_case import AuditLookup
from .laboratory_files_case import LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FOLDER,
    MODEL_LABORATORY_FOLDER_MEMBER,
    MODEL_LABORATORY_SYNC_RULE,
)


@tagged("post_install", "-at_install")
class TestLaboratoryFilesAudit(AuditLookup, LaboratoryFilesCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.auditor = cls.new_auditor()

    def test_creating_a_folder_is_recorded_with_its_owner(self):
        folder = self.env[MODEL_LABORATORY_FOLDER].with_user(self.tester).create({"name": "AAS"})
        owner_row = folder.sudo().member_ids

        created = self.entries(folder, "create")
        self.assertEqual((created.user_id, created.source), (self.tester, "screen"))
        self.assertEqual(self.changes(created)["owner_id"][1], f"{self.tester.name} (#{self.tester.id})")
        row_entry = self.entries(owner_row, "create")
        self.assertEqual((row_entry.parent_model, row_entry.parent_id), (MODEL_LABORATORY_FOLDER, folder.id))

    def test_adding_and_removing_members_is_in_the_folder_history(self):
        members = self.env[MODEL_LABORATORY_FOLDER_MEMBER].with_user(self.administrator)
        row = members.create({"folder_id": self.folder.id, "user_id": self.outsider.id})
        row_id = row.id
        row.unlink()

        history = self.history(self.folder, self.auditor)
        member_entries = history.filtered(
            lambda entry: entry.document_model == MODEL_LABORATORY_FOLDER_MEMBER and entry.document_id == row_id
        )
        self.assertEqual(sorted(member_entries.mapped("action")), ["create", "delete"])
        self.assertEqual(member_entries.user_id, self.administrator)

    def test_turning_off_and_archiving_a_folder_are_recorded(self):
        folder = self.folder.with_user(self.administrator)
        folder.action_turn_off()
        folder.action_archive_folder()

        turned_off, archived = self.entries(self.folder, "edit").sorted("id")
        self.assertEqual(self.changes(turned_off), {"enabled": ("True", "False")})
        self.assertEqual(set(self.changes(archived)), {"archived_at", "retention_until"})
        self.assertEqual((turned_off | archived).user_id, self.administrator)

    def test_changing_the_owner_is_recorded(self):
        self.folder.with_user(self.administrator).owner_id = self.member

        changed = self.entries(self.folder, "edit")
        self.assertEqual(self.changes(changed)["owner_id"][1], f"{self.member.name} (#{self.member.id})")
        roles = self.entries(self.folder.member_ids, "edit")
        self.assertEqual(sorted(self.changes(entry)["role"][1] for entry in roles), ["member", "owner"])

    def test_the_sync_rules_are_in_the_folder_history(self):
        rule = self.env[MODEL_LABORATORY_SYNC_RULE].create({"folder_id": self.folder.id, "pattern": "run-"})

        history = self.history(self.folder, self.auditor)
        self.assertIn(self.entries(rule, "create"), history)
