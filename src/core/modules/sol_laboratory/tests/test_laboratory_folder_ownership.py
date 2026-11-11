from psycopg2 import IntegrityError

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .laboratory_files_case import LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.laboratory_files import MEMBER_ROLE, NOT_ELIGIBLE, OWNER_ROLE
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER


@tagged("post_install", "-at_install")
class TestLaboratoryFolderOwnership(LaboratoryFilesCase):
    def roles(self):
        return {member.user_id: member.role for member in self.folder.member_ids}

    def test_changing_the_owner_keeps_the_previous_owner_as_a_member(self):
        self.folder.with_user(self.administrator).owner_id = self.member

        self.assertEqual(self.folder.owner_id, self.member)
        self.assertEqual(self.roles(), {self.member: OWNER_ROLE, self.tester: MEMBER_ROLE})

    def test_a_new_owner_who_was_not_a_member_becomes_one(self):
        self.folder.with_user(self.administrator).owner_id = self.outsider

        self.assertEqual(self.roles(), {self.outsider: OWNER_ROLE, self.tester: MEMBER_ROLE, self.member: MEMBER_ROLE})

    def test_only_administrators_change_the_owner(self):
        with self.assertRaises(AccessError):
            self.folder.with_user(self.tester).owner_id = self.member

        self.assertEqual(self.folder.owner_id, self.tester)

    def test_the_new_owner_must_be_able_to_use_laboratory_files(self):
        self.assertRefused(
            NOT_ELIGIBLE, self.folder.with_user(self.administrator).write, {"owner_id": self.colleague.id}
        )
        self.assertRefused(
            NOT_ELIGIBLE, self.env[MODEL_LABORATORY_FOLDER].create, {"name": "AAS", "owner_id": self.colleague.id}
        )

    def test_the_new_owner_cannot_already_have_a_folder_of_that_name(self):
        self.env[MODEL_LABORATORY_FOLDER].create({"name": "HPLC", "owner_id": self.member.id})

        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.folder.with_user(self.administrator).owner_id = self.member
            self.folder.flush_recordset()
