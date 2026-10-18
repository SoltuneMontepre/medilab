from odoo.tests import tagged
from odoo.tools import format_date
from odoo.tools.safe_eval import safe_eval, time

from .purchasing_case import PurchasingCase
from odoo.addons.sol_inventory.constants.xml_ids import CONTAINER_LABEL_REPORT, SMALL_CONTAINER_LABEL_REPORT


@tagged("post_install", "-at_install")
class TestContainerLabels(PurchasingCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.receipt = cls.make_receipt((cls.acid, 1000, 1200))
        cls.fill(cls.receipt, cls.acid, ("Lot123", 1000, 2, cls.expiry(), None))
        cls.receipt.button_validate()

    def test_each_label_shows_the_qr_code_code_item_lot_and_usable_date(self):
        containers = self.receipt.container_ids
        for report in (CONTAINER_LABEL_REPORT, SMALL_CONTAINER_LABEL_REPORT):
            html = self.env["ir.actions.report"]._render_qweb_html(report, containers.ids)[0].decode()
            for container in containers:
                self.assertIn(f'alt="Barcode {container.name}"', html)
            self.assertIn(self.acid.name, html)
            self.assertIn("Lot123", html)
            self.assertIn(format_date(self.env, containers[0].usable_until), html)

    def test_a_receipt_prints_the_labels_of_its_containers(self):
        for action in (
            self.receipt.action_print_container_labels(),
            self.receipt.action_print_small_container_labels(),
        ):
            self.assertEqual(action["context"]["active_ids"], self.receipt.container_ids.ids)

    def test_the_labels_of_one_container_are_named_after_it(self):
        # Odoo names a downloaded report only when it holds one record, and gives the name only that record.
        container = self.receipt.container_ids[:1]
        for report in (CONTAINER_LABEL_REPORT, SMALL_CONTAINER_LABEL_REPORT):
            name = safe_eval(self.env.ref(report).print_report_name, {"object": container, "time": time})
            self.assertEqual(name, f"Labels {container.name}")
