from lxml import etree

from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_PARAMETER


@tagged("post_install", "-at_install")
class TestWaysOfTestingList(TransactionCase):
    def test_ways_of_testing_list_offers_archiving_but_not_deleting(self):
        arch = self.env[MODEL_TEST_PARAMETER].get_views([(False, "form")])["views"]["form"]["arch"]
        rows = etree.fromstring(arch).xpath("//field[@name='method_ids']/list")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].get("delete"), "0")
        self.assertTrue(rows[0].xpath("field[@name='active']"))
