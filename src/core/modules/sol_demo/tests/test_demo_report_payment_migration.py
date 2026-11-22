from pathlib import Path

from odoo.modules.module import load_script
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER
from odoo.addons.sol_laboratory.tests.report_case import ReportCase

POST_MIGRATE = Path(__file__).resolve().parents[1] / "migrations" / "20.0.1.45.0" / "post-migrate.py"


@tagged("post_install", "-at_install")
class TestDemoReportPaymentMigration(HttpCase, ReportCase):
    """An upgraded demo pays report orders through accounting before delivery and portal release."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        contact = cls.env["res.partner"].create(
            {"name": "Bui Thi Mai", "parent_id": cls.customer.partner_id.id, "email": "mai@anphu.example"}
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Lead test", "type": "service", "invoice_policy": "order", "list_price": 1_000_000}
        )
        cls.contact = contact
        cls.portal = new_test_user(cls.env, "mai.upgrade", groups="base.group_portal", partner_id=contact.id)
        other = cls.env[MODEL_CUSTOMER].create({"name": "Green Farm Co., Ltd.", "is_company": True})
        cls.foreign = new_test_user(cls.env, "farm.upgrade", groups="base.group_portal", partner_id=other.partner_id.id)
        cls.portal.password = cls.portal.login
        cls.foreign.password = cls.foreign.login

    def issue_scheduled_report(self, delivery_method):
        self.request.delivery_method = delivery_method
        booking = self.schedule(self.test, self.tester)
        self.complete()
        self.sign()
        report = self.report()
        self.assertTrue(booking)
        self.assertEqual(self.test.sample_id.request_id, report.request_id)
        return report

    def link_unpaid_order(self, report):
        order = self.env[MODEL_SALE_ORDER].create(
            {
                "partner_id": self.contact.id,
                "customer_id": self.customer.partner_id.id,
                "source": "sales",
                "order_status": "completed",
                "test_request_id": report.request_id.id,
                "order_line": [(0, 0, {"product_id": self.product.id, "price_unit": 1_000_000, "tax_ids": False})],
            }
        )
        report.invalidate_recordset(["withheld_for_payment", "withheld_order_name"])
        return order

    def migrate(self):
        self.assertTrue(POST_MIGRATE.is_file(), "The demo report payment upgrade migration must exist.")
        load_script(str(POST_MIGRATE), "demo_report_payment_post").migrate(self.env.cr, "20.0.1.44.0")
        self.env.invalidate_all()

    def counters(self, user):
        self.authenticate(user.login, user.login)
        return self.make_jsonrpc_request("/my/counters", {"counters": {"test_report_count": "client_category"}})

    def download(self, user, report):
        self.authenticate(user.login, user.login)
        return self.url_open(f"/my/test-reports/{report.id}/download")

    def test_upgrade_releases_one_scheduled_request_through_postal_delivery_and_owner_download(self):
        report = self.issue_scheduled_report("post")
        self.assertFalse(report.withheld_for_payment)
        order = self.link_unpaid_order(report)

        self.assertTrue(report.withheld_for_payment)
        self.assertEqual(self.counters(self.portal)["test_report_count"], 0)
        self.assertEqual(self.download(self.portal, report).status_code, 404)

        self.migrate()
        invoices = order.invoice_ids

        self.assertEqual(order.payment_status, "paid")
        self.assertFalse(report.withheld_for_payment)
        self.assertEqual(self.counters(self.portal)["test_report_count"], 1)
        response = self.download(self.portal, report)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, bytes(report.attachment_id.raw))
        self.assertEqual(self.download(self.foreign, report).status_code, 404)

        self.migrate()
        self.assertEqual(order.invoice_ids, invoices)

        report.with_user(self.courier.user_id).action_record_delivery()
        self.assertTrue(report.delivered_at)
        self.assertEqual(report.request_id.status, "reported")

    def test_upgrade_releases_one_scheduled_request_for_in_person_delivery(self):
        report = self.issue_scheduled_report("in_person")
        self.assertFalse(report.withheld_for_payment)
        self.link_unpaid_order(report)

        self.assertTrue(report.withheld_for_payment)
        self.migrate()

        report.with_user(self.courier.user_id).action_record_delivery()

        self.assertFalse(report.withheld_for_payment)
        self.assertTrue(report.delivered_at)
        self.assertFalse(
            self.env["mail.message"].search([("notification_key", "=", f"test_report:{report.id}:delivered")])
        )
