from odoo.tests import tagged

from .laboratory_files_case import LaboratoryFilesCase
from odoo.addons.sol_laboratory.constants.laboratory_files import RAW_DATA
from odoo.addons.sol_laboratory.constants.models import MODEL_LABORATORY_FOLDER


@tagged("post_install", "-at_install")
class TestLaboratoryFileKinds(LaboratoryFilesCase):
    def test_raw_data_is_a_file_of_a_raw_data_folder(self):
        raw_data = self.env[MODEL_LABORATORY_FOLDER].create(
            {"name": "Raw data", "owner_id": self.tester.id, "category": RAW_DATA}
        )
        results = self.env[MODEL_LABORATORY_FOLDER].create(
            {"name": "Results", "owner_id": self.tester.id, "category": "result"}
        )

        self.assertTrue(self.file_of("run-01.csv", raw_data)._is_raw_data())
        self.assertFalse(self.file_of("run-01.csv", results)._is_raw_data())
        self.assertFalse(self.file_of("run-01.csv")._is_raw_data())

    def test_office_documents_are_word_excel_and_powerpoint_files_whatever_their_letter_case(self):
        office = ("report.docx", "Results/HPLC.XLSX", "Talk.PpTx")
        others = ("run-01.csv", "notes.doc", "sheet.xls", "report.odt", ".xlsx", "README")

        for path in office:
            with self.subTest(path=path):
                self.assertTrue(self.file_of(path)._is_office_document())
        for path in others:
            with self.subTest(path=path):
                self.assertFalse(self.file_of(path)._is_office_document())
