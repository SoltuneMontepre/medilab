from datetime import date, timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_QUOTATION_SEND, MODEL_SAMPLE_COLLECTION_START
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST, MODEL_TEST_REQUEST


@tagged("post_install", "-at_install")
class TestQuotationSendDialog(OrderCase):
    """Sales agrees the payment deadline and the sample pickup day with the customer when sending the quotation; Lead
    is tested in 5 working days."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.parameter.method_ids.turnaround_days = 5

    def dialog(self, order):
        action = order.with_user(self.sales).with_context(medilab_quotation_dialog=True).action_send_quotation()
        self.assertEqual(action["res_model"], MODEL_QUOTATION_SEND)
        return Form(self.env[MODEL_QUOTATION_SEND].with_user(self.sales).with_context(action["context"]))

    def test_the_button_asks_for_the_deadline_and_the_pickup_before_sending(self):
        order = self.make_quotable_order()
        pickup = date.today() + timedelta(days=3)

        form = self.dialog(order)
        self.assertGreater(form.payment_deadline, fields.Datetime.now())
        self.assertFalse(order.quotation_ids)
        form.expected_collection_date = pickup
        form.save().action_send()

        self.assertEqual(order.expected_collection_date, pickup)
        self.assertEqual(order._latest_quotation().status, "sent")

    def test_the_estimate_counts_from_the_pickup_day(self):
        order = self.make_quotable_order()
        pickup = date.today() + timedelta(days=21)
        requests = self.env[MODEL_TEST_REQUEST]

        form = self.dialog(order)
        form.expected_collection_date = pickup

        self.assertGreaterEqual(form.estimated_result_date, requests._date_after_working_days(pickup, 5))
        self.assertLess(order.estimated_result_date, form.estimated_result_date)

    def test_a_requested_date_before_the_pickup_estimate_is_not_promised(self):
        # Picked up today the samples would meet the requested date; picked up in three weeks they would not.
        order = self.make_quotable_order()
        requests = self.env[MODEL_TEST_REQUEST]
        order.requested_date = requests._date_after_working_days(date.today() + timedelta(days=1), 5)

        form = self.dialog(order)
        form.expected_collection_date = date.today() + timedelta(days=21)
        form.save().action_send()

        self.assertFalse(order.committed_date)

    def test_a_past_pickup_day_is_refused(self):
        order = self.make_quotable_order()

        form = self.dialog(order)
        form.expected_collection_date = date.today() - timedelta(days=1)

        with self.assertRaisesRegex(UserError, "pickup day"):
            form.save().action_send()
        self.assertFalse(order.quotation_ids)

    def test_the_collection_appointment_starts_on_the_pickup_day(self):
        order = self.make_quotable_order()
        pickup = date.today() + timedelta(days=3)
        form = self.dialog(order)
        form.expected_collection_date = pickup
        form.save().action_send()

        start = (
            self.env[MODEL_SAMPLE_COLLECTION_START]
            .with_user(self.sales)
            .with_context(default_order_id=order.id)
            .default_get(["appointment"])
        )

        self.assertEqual(self.env[MODEL_SAMPLE_TEST]._local_day(start["appointment"]), pickup)
