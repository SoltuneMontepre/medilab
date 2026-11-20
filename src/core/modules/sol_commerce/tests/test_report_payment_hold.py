from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_REPORT
from odoo.addons.sol_laboratory.tests.change_request_case import ChangeRequestCase


@tagged("post_install", "-at_install")
class TestReportPaymentHold(ChangeRequestCase):
    """The order of 1,000,000 VND is confirmed with nothing paid; its report is issued but reaches the customer only
    once the order is paid in full, unless the order is on credit."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        contact = cls.env["res.partner"].create(
            {"name": "Bui Thi Mai", "parent_id": cls.customer.partner_id.id, "email": "mai@anphu.example"}
        )
        product = cls.env["product.product"].create(
            {"name": "Lead test", "type": "service", "invoice_policy": "order", "list_price": 1_000_000}
        )
        cls.order = cls.env[MODEL_SALE_ORDER].create(
            {
                "partner_id": contact.id,
                "customer_id": cls.customer.partner_id.id,
                "source": "sales",
                "state": "sale",
                "order_status": "confirmed",
                "test_request_id": cls.request.id,
                "order_line": [(0, 0, {"product_id": product.id, "price_unit": 1_000_000, "tax_ids": False})],
            }
        )
        cls.portal_user = new_test_user(cls.env, "mai.hold", groups="base.group_portal", partner_id=contact.id)

    def issue(self):
        self.complete()
        self.sign()
        return self.report()

    def offered(self, report):
        reports = self.env[MODEL_TEST_REPORT]
        return report in reports.sudo().search(reports._portal_domain(self.portal_user))

    def pay(self):
        invoice = self.order._draft_final_invoice()
        invoice.action_post()
        self.env["account.payment.register"].with_context(active_model="account.move", active_ids=invoice.ids).create(
            {}
        ).action_create_payments()

    def test_the_report_of_an_unpaid_order_is_issued_but_withheld(self):
        report = self.issue()

        self.assertEqual(report.status, "issued")
        self.assertTrue(report.withheld_for_payment)
        self.assertEqual(report.withheld_order_name, self.order.name)
        self.assertFalse(self.offered(report))
        with self.assertRaisesRegex(UserError, "paid in full"):
            self.as_person(report, self.courier).action_record_delivery()

    def test_issuing_tells_the_customer_the_report_waits_for_payment(self):
        self.issue()

        notice = self.messages(self.order).filtered(lambda message: "paid in full" in (message.body or ""))
        self.assertTrue(notice)

    def test_paying_in_full_releases_the_report(self):
        report = self.issue()

        self.pay()
        self.order.invalidate_recordset(["payment_status"])
        report.invalidate_recordset(["withheld_for_payment"])

        self.assertFalse(report.withheld_for_payment)
        self.assertTrue(self.offered(report))
        self.as_person(report, self.courier).action_record_delivery()
        self.assertTrue(report.delivered_at)

    def test_an_order_on_credit_gets_its_report_before_paying(self):
        self.order.on_credit = True

        report = self.issue()

        self.assertFalse(report.withheld_for_payment)
        self.assertTrue(self.offered(report))
