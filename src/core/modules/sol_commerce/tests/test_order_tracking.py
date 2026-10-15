from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_laboratory.tests.report_case import ReportCase


@tagged("post_install", "-at_install")
class TestOrderTracking(ReportCase):
    """An order follows its test request through testing, and its contact is told once when the results are
    released."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contact = cls.env["res.partner"].create(
            {"name": "Bui Thi Mai", "parent_id": cls.customer.partner_id.id, "email": "mai@anphu.example"}
        )
        cls.order = cls.env[MODEL_SALE_ORDER].create(
            {
                "partner_id": cls.contact.id,
                "customer_id": cls.customer.partner_id.id,
                "source": "sales",
                "order_status": "confirmed",
                "user_id": cls.create_person("Nguyen Thi Thu", login="thu.tracking").user_id.id,
                "test_request_id": cls.request.id,
            }
        )

    def progress(self):
        self.order.invalidate_recordset(["customer_status"])
        return self.order.customer_status

    def test_the_order_shows_waiting_testing_then_completed_and_completes_with_the_report(self):
        self.assertEqual(self.progress(), "waiting")

        result = self.enter()
        self.assertEqual(self.progress(), "testing")

        self.send(result)
        self.approve(result)
        self.assertEqual((self.request.status, self.progress()), ("completed", "completed"))
        self.assertEqual(self.order.order_status, "confirmed")

        self.sign()
        self.assertEqual((self.order.order_status, self.progress()), ("completed", "completed"))

    def test_a_cancellation_request_cannot_cancel_an_order_whose_results_are_released(self):
        cancellation = self.order.action_request_cancellation("We no longer need the tests.")
        self.complete()
        self.sign()

        with self.assertRaises(UserError):
            cancellation.action_accept()
        self.assertEqual(self.order.order_status, "completed")

    def test_the_orders_contact_is_told_once_on_the_order_when_the_results_are_released(self):
        self.complete()
        report = self.report()

        self.sign(report)
        report._notify_issued()

        event = self.env.ref("sol_laboratory.event_test_report_issued")
        on_order = self.env["mail.message"].search(
            [("model", "=", MODEL_SALE_ORDER), ("res_id", "=", self.order.id), ("subtype_id", "=", event.id)]
        )
        self.assertEqual(len(on_order), 1)
        self.assertEqual(on_order.notification_ids.res_partner_id, self.contact)
        self.assertIn(self.order.name, on_order.body)
        self.assertFalse(
            self.env["mail.message"].search(
                [("model", "=", report._name), ("res_id", "=", report.id), ("subtype_id", "=", event.id)]
            )
        )
