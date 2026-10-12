from odoo.tests import tagged
from odoo.tools import format_date

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.xml_ids import SAMPLE_LABEL_REPORT


@tagged("post_install", "-at_install")
class TestSampleLabel(RequestCase):
    def test_label_shows_codes_due_date_and_qr_code_but_not_the_customer(self):
        html = self.env["ir.actions.report"]._render_qweb_html(SAMPLE_LABEL_REPORT, self.sample.ids)[0].decode()
        due_date = self.sample.test_ids.due_date

        self.assertIn(self.sample.code, html)
        self.assertIn(self.request.code, html)
        self.assertIn(format_date(self.env, due_date), html)
        self.assertIn(f'alt="Barcode {self.sample.code}"', html)
        self.assertNotIn(self.customer.name, html)
        self.assertNotIn(self.sample.customer_sample_name, html)

    def test_request_prints_the_labels_of_its_samples(self):
        action = self.request.action_print_labels()

        self.assertEqual(action["report_name"], "sol_laboratory.report_sample_label")
        self.assertEqual(action["context"]["active_ids"], self.sample.ids)
