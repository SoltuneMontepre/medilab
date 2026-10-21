from psycopg2 import IntegrityError

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .laboratory_files_case import LaboratoryFilesCase
from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.laboratory_files import RAW_DATA
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER


@tagged("post_install", "-at_install")
class TestLaboratorySampleFolderRecords(LaboratoryFilesCase, RequestCase):
    def create_folder(self, name, **vals):
        return self.env[MODEL_LABORATORY_FOLDER].create({"name": name, "owner_id": self.tester.id, **vals})

    def test_a_sample_has_one_folder_of_each_category(self):
        self.create_folder("Raw data", sample_id=self.sample.id, category=RAW_DATA)
        self.create_folder("Results", sample_id=self.sample.id, category="result")

        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            self.create_folder("Raw data again", sample_id=self.sample.id, category=RAW_DATA)

    def test_folders_of_no_sample_are_not_limited_by_category(self):
        self.create_folder("HPLC raw data", category=RAW_DATA)

        self.create_folder("GC raw data", category=RAW_DATA)

    def test_a_folder_of_a_sample_needs_a_category(self):
        with mute_logger("odoo.sql_db"), self.assertRaises(IntegrityError):
            self.create_folder("Unsorted", sample_id=self.sample.id)

    def test_a_folder_keeps_its_sample_and_category_once_it_holds_files(self):
        other_sample = self.create_request().sample_ids
        folder = self.create_folder("Results", sample_id=self.sample.id, category="result")
        folder.category = "working"
        self.save(self.file_of("result.xlsx", folder), "result 1")

        for vals in ({"sample_id": other_sample.id}, {"category": "result"}, {"sample_id": False, "category": False}):
            with self.subTest(vals=vals), self.assertRaises(UserError):
                folder.write(vals)
        folder.write({"name": "Results of the lead test", "category": "working"})
        self.assertEqual(folder.sample_id, self.sample)
