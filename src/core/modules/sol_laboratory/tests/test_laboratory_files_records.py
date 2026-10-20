from psycopg2 import IntegrityError

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .laboratory_files_case import LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.laboratory_files import MEMBER_ROLE, OWNER_ROLE, UPLOAD_ONLY
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_DEVICE,
    MODEL_LABORATORY_FOLDER,
    MODEL_LABORATORY_FOLDER_MEMBER,
)


@tagged("post_install", "-at_install")
class TestLaboratoryFilesRecords(LaboratoryFilesCase):
    def test_creating_a_folder_makes_its_owner_a_member(self):
        roles = {member.user_id: member.role for member in self.folder.member_ids}

        self.assertEqual(roles, {self.tester: OWNER_ROLE, self.member: MEMBER_ROLE})
        self.assertEqual(self.folder.root, "HPLC")
        self.assertEqual(self.folder.sync_mode, UPLOAD_ONLY)
        self.assertTrue(self.folder.enabled)

    def test_an_owner_has_one_folder_of_each_name(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.env[MODEL_LABORATORY_FOLDER].create({"name": "HPLC", "owner_id": self.tester.id})

    def test_another_owner_may_use_the_same_name(self):
        folder = self.env[MODEL_LABORATORY_FOLDER].create({"name": "HPLC", "owner_id": self.member.id})

        self.assertEqual(folder.root, "HPLC")

    def test_renaming_a_folder_keeps_the_name_it_was_created_with(self):
        self.folder.name = "HPLC results"

        self.assertEqual(self.folder.root, "HPLC")
        with self.assertRaises(UserError):
            self.folder.root = "HPLC results"

    def test_a_folder_has_one_owner(self):
        row = self.folder.member_ids.filtered(lambda member: member.user_id == self.member)

        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            row.role = OWNER_ROLE
            row.flush_recordset()

    def test_the_owner_cannot_be_removed_from_the_folder(self):
        owner_row = self.folder.member_ids.filtered(lambda member: member.role == OWNER_ROLE)

        with self.assertRaises(UserError):
            owner_row.unlink()
        self.assertTrue(owner_row.exists())

    def test_a_person_is_a_member_of_a_folder_once(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            self.env[MODEL_LABORATORY_FOLDER_MEMBER].create({"folder_id": self.folder.id, "user_id": self.member.id})

    def test_an_installation_is_one_device_per_person(self):
        devices = self.env[MODEL_LABORATORY_DEVICE]
        values = {"client_uid": "4f1c2b8e-0d1a-4a8e-9c55-3b7f6f1e2a10", "name": "HPLC-PC", "platform": "windows"}
        devices.create({**values, "user_id": self.tester.id})
        devices.create({**values, "user_id": self.member.id})

        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            devices.create({**values, "user_id": self.tester.id})
