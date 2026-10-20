from odoo.fields import Command
from odoo.tests import tagged

from .laboratory_files_case import LaboratoryFilesCase
from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.laboratory_files import FILE_READ, FOLDER_READ, NOT_FOUND
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER

SAMPLE_READER_GROUP = "sol_laboratory.group_permission_sample_read_all"


@tagged("post_install", "-at_install")
class TestLaboratorySampleFolderAccess(LaboratoryFilesCase, RequestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.raw_data = cls.env[MODEL_LABORATORY_FOLDER].create(
            {"name": "Raw data", "owner_id": cls.tester.id, "sample_id": cls.sample.id, "category": "raw"}
        )

    def test_a_member_who_cannot_see_the_sample_gets_nothing_from_its_folder(self):
        self.assertRefused(NOT_FOUND, self.raw_data.with_user(self.tester)._check_folder_access, FOLDER_READ)

    def test_a_member_who_can_see_the_sample_reads_its_folder(self):
        self.tester.group_ids = [Command.link(self.env.ref(SAMPLE_READER_GROUP).id)]

        self.raw_data.with_user(self.tester)._check_folder_access(FOLDER_READ)

    def test_the_files_of_a_sample_folder_need_the_sample_too(self):
        file = self.file_of("HPLC/run-01.csv", self.raw_data)

        self.assertRefused(NOT_FOUND, file.with_user(self.tester)._check_file_access, FILE_READ)
        self.tester.group_ids = [Command.link(self.env.ref(SAMPLE_READER_GROUP).id)]
        file.with_user(self.tester)._check_file_access(FILE_READ)
        self.assertTrue(file._is_raw_data())
