from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import format_date

from .request_case import RequestCase
from odoo.addons.sol_laboratory.constants.xml_ids import SAMPLE_LABEL_REPORT


@tagged("post_install", "-at_install")
class TestSampleLabel(RequestCase):
    def test_label_shows_codes_due_date_and_qr_code_but_not_the_customer(self):
        self.handover_for(self.sample).action_sign(b"signature-bytes")
        html = self.env["ir.actions.report"]._render_qweb_html(SAMPLE_LABEL_REPORT, self.sample.ids)[0].decode()
        due_date = self.sample.test_ids.due_date

        self.assertIn(self.sample.code, html)
        self.assertIn(self.request.code, html)
        self.assertIn(format_date(self.env, due_date), html)
        self.assertIn(f'alt="Barcode {self.sample.code}"', html)
        self.assertNotIn(self.customer.name, html)
        self.assertNotIn(self.sample.customer_sample_name, html)

    def test_printing_waits_for_the_same_samples_signed_handover(self):
        draft = self.handover_for(self.sample)
        other = self.sample.copy({"request_id": self.request.id})
        self.handover_for(other).action_sign(b"signature-bytes")

        report = self.env["ir.actions.report"]
        with self.assertRaisesRegex(UserError, "sign the handover"):
            report._render_qweb_html(SAMPLE_LABEL_REPORT, (self.sample | other).ids)
        self.assertEqual(self.request.action_print_labels()["context"]["active_ids"], other.ids)

        draft.action_sign(b"signature-bytes")
        action = self.request.action_print_labels()
        self.assertEqual(action["report_name"], "sol_laboratory.report_sample_label")
        self.assertCountEqual(action["context"]["active_ids"], (self.sample | other).ids)

    def test_printing_without_a_signed_handover_is_refused(self):
        with self.assertRaisesRegex(UserError, "sign the handover"):
            self.request.action_print_labels()
        self.handover_for(self.sample)
        with self.assertRaisesRegex(UserError, "sign the handover"):
            self.request.action_print_labels()
