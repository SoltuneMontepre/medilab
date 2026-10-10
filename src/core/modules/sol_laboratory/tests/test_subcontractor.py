from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.constants.models import MODEL_SUBCONTRACTOR


@tagged("post_install", "-at_install")
class TestSubcontractor(TransactionCase):
    def test_new_subcontractor_is_a_company(self):
        subcontractor_id, _name = self.env[MODEL_SUBCONTRACTOR].name_create("Northern Testing Laboratory")

        self.assertTrue(self.env[MODEL_SUBCONTRACTOR].browse(subcontractor_id).is_company)
