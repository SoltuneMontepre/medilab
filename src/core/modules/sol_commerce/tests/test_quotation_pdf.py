import re
from unittest.mock import patch

from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.base.models.ir_actions_report import IrActionsReport
from odoo.addons.sol_commerce.constants.xml_ids import QUOTATION_REPORT


@tagged("post_install", "-at_install")
class TestQuotationPdf(OrderCase):
    def html(self, order):
        html = self.env["ir.actions.report"]._render_qweb_html(QUOTATION_REPORT, order.ids)[0].decode()
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))

    def test_the_sent_pdf_is_rendered_with_the_quotation_number(self):
        order = self.make_quotable_order()
        rendered = []
        original = IrActionsReport._render_qweb_pdf

        def render(report, *args, **kwargs):
            rendered.append(report.env.context.get("quotation_code"))
            return original(report, *args, **kwargs)

        with patch.object(IrActionsReport, "_render_qweb_pdf", render):
            order.with_user(self.sales).action_send_quotation()

        self.assertEqual(rendered, [order._latest_quotation().code])

    def test_the_title_carries_the_quotation_number_not_the_order_number(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()

        text = self.html(order)

        self.assertIn(f"# {order._latest_quotation().code}", text)
        self.assertNotIn(f"# {order.name}", text)

    def test_the_salesperson_is_not_labelled_contact(self):
        order = self.make_quotable_order()

        self.assertNotIn("Contact", self.html(order))
        self.assertIn("Salesperson", self.html(order))

    def test_quantity_has_no_unit(self):
        order = self.make_quotable_order()

        self.assertNotIn("Units", self.html(order))

    def test_the_report_renders_in_the_contact_language(self):
        order = self.make_quotable_order()
        order.partner_id.lang = "vi_VN"

        self.assertIn("Nhân viên kinh doanh", self.html(order))
