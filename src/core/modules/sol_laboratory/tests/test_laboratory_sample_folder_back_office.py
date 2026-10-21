from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import tagged

from .laboratory_files_case import LaboratoryFilesCase
from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.laboratory_files import MEMBER_ROLE, RAW_DATA, RESULT
from odoo.addons.sol_laboratory.constants.models import (
    MODEL_LABORATORY_FILE,
    MODEL_LABORATORY_FILE_CHANGE,
    MODEL_LABORATORY_FILE_LOCK,
    MODEL_LABORATORY_FILE_VERSION,
    MODEL_LABORATORY_FOLDER,
    MODEL_LABORATORY_FOLDER_MEMBER,
    MODEL_LABORATORY_SYNC_RULE,
    MODEL_SAMPLE,
)
from odoo.addons.sol_laboratory.constants.xml_ids import FOLDER_ADMINISTRATION_GROUP

SAMPLE_READER_GROUP = "sol_laboratory.group_permission_sample_read_all"
# The groups of a folder administrator who reads every folder and what it holds, but no sample.
FOLDER_ADMINISTRATOR_GROUPS = (
    FOLDER_ADMINISTRATION_GROUP,
    "sol_laboratory.group_permission_laboratory_folder_read_all",
    "sol_laboratory.group_permission_laboratory_folder_member_read_all",
    "sol_laboratory.group_permission_laboratory_sync_rule_read_all",
    "sol_laboratory.group_permission_laboratory_file_read_all",
    "sol_laboratory.group_permission_laboratory_file_version_read_all",
    "sol_laboratory.group_permission_laboratory_file_change_read_all",
    "sol_laboratory.group_permission_laboratory_file_lock_read_all",
)


@tagged("post_install", "-at_install")
class TestLaboratorySampleFolderBackOffice(LaboratoryFilesCase, RequestCase):
    """The raw-data folder of the lead sample, which the second tester is a member of, with a rule and a saved file,
    next to the HPLC folder of no sample."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.folder_administrator = cls.create_user("lab.folders", *FOLDER_ADMINISTRATOR_GROUPS)
        cls.raw_data = cls.env[MODEL_LABORATORY_FOLDER].create(
            {
                "name": "Raw data",
                "owner_id": cls.tester.id,
                "sample_id": cls.sample.id,
                "category": RAW_DATA,
                "member_ids": [Command.create({"user_id": cls.member.id, "role": MEMBER_ROLE})],
                "rule_ids": [Command.create({"kind": "extension", "pattern": "csv"})],
            }
        )

    def setUp(self):
        super().setUp()
        sample_file = self.file_of("HPLC/run-01.csv", self.raw_data)
        self.save(sample_file, "run 1")
        other_file = self.file_of("HPLC/run-02.csv")
        self.save(other_file, "run 2")
        self.records = {
            MODEL_LABORATORY_FOLDER: (self.raw_data, self.folder),
            MODEL_LABORATORY_FOLDER_MEMBER: (self.raw_data.member_ids, self.folder.member_ids),
            MODEL_LABORATORY_SYNC_RULE: (self.raw_data.rule_ids, self.folder.rule_ids),
            MODEL_LABORATORY_FILE: (sample_file, other_file),
            MODEL_LABORATORY_FILE_VERSION: (sample_file.version_ids, other_file.version_ids),
            MODEL_LABORATORY_FILE_CHANGE: (
                self.env[MODEL_LABORATORY_FILE_CHANGE].search([("folder_id", "=", self.raw_data.id)]),
                self.env[MODEL_LABORATORY_FILE_CHANGE].search([("folder_id", "=", self.folder.id)]),
            ),
        }

    def visible(self, user, model, records):
        return self.env[model].with_user(user).search([("id", "in", records.ids)])

    def member_records(self):
        # Members do not read changes; computers get them through the laboratory files API.
        return {model: records for model, records in self.records.items() if model != MODEL_LABORATORY_FILE_CHANGE}

    def test_a_member_who_cannot_see_the_sample_sees_nothing_of_its_folder(self):
        for model, (of_sample, of_no_sample) in self.member_records().items():
            with self.subTest(model=model):
                self.assertFalse(self.visible(self.member, model, of_sample))
                self.assertEqual(self.visible(self.member, model, of_no_sample), of_no_sample)
                with self.assertRaises(AccessError):
                    of_sample.with_user(self.member).read(["display_name"])

    def test_a_member_who_sees_the_sample_sees_its_folder(self):
        self.member.group_ids = [Command.link(self.env.ref(SAMPLE_READER_GROUP).id)]

        for model, (of_sample, _of_no_sample) in self.member_records().items():
            with self.subTest(model=model):
                self.assertEqual(self.visible(self.member, model, of_sample), of_sample)

    def test_a_folder_administrator_needs_the_sample_too(self):
        for model, (of_sample, of_no_sample) in self.records.items():
            with self.subTest(model=model):
                self.assertFalse(self.visible(self.folder_administrator, model, of_sample))
                self.assertEqual(self.visible(self.folder_administrator, model, of_no_sample), of_no_sample)

        self.folder_administrator.group_ids = [Command.link(self.env.ref(SAMPLE_READER_GROUP).id)]
        for model, (of_sample, _of_no_sample) in self.records.items():
            with self.subTest(model=model, sees_sample=True):
                self.assertEqual(self.visible(self.folder_administrator, model, of_sample), of_sample)

    def test_a_lock_in_a_folder_of_the_sample_is_hidden_from_people_who_cannot_see_the_sample(self):
        results = self.env[MODEL_LABORATORY_FOLDER].create(
            {
                "name": "Results",
                "owner_id": self.tester.id,
                "sample_id": self.sample.id,
                "category": RESULT,
                "member_ids": [Command.create({"user_id": self.member.id, "role": MEMBER_ROLE})],
            }
        )
        sample_file = self.file_of("lead.csv", results)
        self.save(sample_file, "lead 1")
        other_file = self.file_of("calibration.csv")
        self.save(other_file, "calibration 1")
        # Locking the sample's file takes seeing the sample too.
        self.tester.group_ids = [Command.link(self.env.ref(SAMPLE_READER_GROUP).id)]
        of_sample = sample_file.with_user(self.tester)._lock()
        of_no_sample = other_file.with_user(self.tester)._lock()

        for user in (self.member, self.folder_administrator):
            with self.subTest(user=user.login):
                self.assertEqual(self.visible(user, MODEL_LABORATORY_FILE_LOCK, of_sample | of_no_sample), of_no_sample)
                with self.assertRaises(AccessError):
                    of_sample.with_user(user).read(["display_name"])

            user.group_ids = [Command.link(self.env.ref(SAMPLE_READER_GROUP).id)]
            with self.subTest(user=user.login, sees_sample=True):
                self.assertEqual(
                    self.visible(user, MODEL_LABORATORY_FILE_LOCK, of_sample | of_no_sample), of_sample | of_no_sample
                )

    def test_a_folder_administrator_who_cannot_see_the_sample_cannot_change_its_folder(self):
        with self.assertRaises(AccessError):
            self.raw_data.with_user(self.folder_administrator).write({"name": "Raw data of the lead sample"})

    def test_the_sample_counts_only_the_folders_the_person_sees(self):
        for user in (self.member, self.outsider):
            user.group_ids = [Command.link(self.env.ref(SAMPLE_READER_GROUP).id)]

        self.assertEqual(
            self.env[MODEL_SAMPLE].with_user(self.member).browse(self.sample.id).laboratory_folder_count, 1
        )
        self.assertEqual(
            self.env[MODEL_SAMPLE].with_user(self.outsider).browse(self.sample.id).laboratory_folder_count, 0
        )
