from odoo.tests import tagged

from .audit_case import AuditCase
from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ATTACHMENT, MODEL_REGULATION


@tagged("post_install", "-at_install")
class TestAuditFiles(AuditCase):
    def attach(self, **values):
        return self.env[MODEL_IR_ATTACHMENT].create({"name": "certificate.pdf", "raw": b"%PDF-1.4", **values})

    def test_a_file_of_a_document_is_recorded_without_its_content(self):
        file = self.attach(res_model=MODEL_REGULATION, res_id=self.regulation.id)

        changes = self.changes(self.entries(file, "create"))
        self.assertEqual(changes["res_model"], (False, MODEL_REGULATION))
        self.assertEqual(changes["res_id"], (False, str(self.regulation.id)))
        self.assertTrue(changes["checksum"][1])
        self.assertFalse({"raw", "datas", "db_datas", "store_fname", "index_content"} & set(changes))

    def test_the_history_of_a_document_includes_its_files_once_deleted(self):
        file = self.attach(res_model=MODEL_REGULATION, res_id=self.regulation.id)
        file.name = "certificate-2026.pdf"
        entries = self.entries(file)

        file.unlink()

        history = self.history(self.regulation, self.auditor)
        self.assertLessEqual(entries | self.entries(file, "delete"), history)

    def test_odoos_own_files_are_not_recorded(self):
        unattached = self.attach()
        stored_field = self.attach(res_model=MODEL_REGULATION, res_id=self.regulation.id, res_field="name")

        self.assertFalse(self.entries(unattached | stored_field))

    def test_a_file_attached_to_a_document_later_is_recorded_as_created(self):
        file = self.attach()

        file.write({"res_model": MODEL_REGULATION, "res_id": self.regulation.id})

        self.assertEqual(self.changes(self.entries(file, "create"))["res_model"], (False, MODEL_REGULATION))
        self.assertFalse(self.entries(file, "edit"))
