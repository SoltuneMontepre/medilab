from odoo.tests import tagged

from .stores_case import StoresCase
from odoo.addons.sol_laboratory.tests.audit_case import AuditLookup


@tagged("post_install", "-at_install")
class TestAuditDocuments(AuditLookup, StoresCase):
    def test_every_inventory_document_is_audited(self):
        self.assertEqual(self.unaudited_documents("sol_inventory"), set())

    def test_changing_a_store_is_audited(self):
        self.chemistry_store.conditions = "18-22 °C"

        entry = self.entries(self.chemistry_store, "edit")
        self.assertEqual(len(entry), 1)
        self.assertEqual(self.changes(entry)["conditions"][1], "18-22 °C")
