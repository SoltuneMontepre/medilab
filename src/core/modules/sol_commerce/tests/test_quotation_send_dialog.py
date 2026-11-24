from datetime import date, datetime, timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_QUOTATION_SEND, MODEL_SAMPLE_COLLECTION_START
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TEST, MODEL_TEST_REQUEST


@tagged("post_install", "-at_install")
class TestQuotationSendDialog(OrderCase):
    """Sales sets the quotation's prices, discounts, payment and recipient when sending the quotation; Lead is tested
    in 5 working days."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.parameter.method_ids.turnaround_days = 5

    def dialog(self, order):
        action = order.with_user(self.sales).with_context(medilab_quotation_dialog=True).action_send_quotation()
        self.assertEqual(action["res_model"], MODEL_QUOTATION_SEND)
        return Form(self.env[MODEL_QUOTATION_SEND].with_user(self.sales).with_context(**action["context"]))

    def test_the_button_asks_for_the_deadline_before_sending(self):
        order = self.make_quotable_order()

        form = self.dialog(order)
        deadline = form.payment_deadline
        assert isinstance(deadline, datetime)
        self.assertGreater(deadline, fields.Datetime.now())
        self.assertFalse(order.quotation_ids)
        form.save().action_send()

        self.assertEqual(order._latest_quotation().status, "sent")

    def test_the_expected_return_date_counts_from_the_pickup_day(self):
        order = self.make_quotable_order()
        pickup = date.today() + timedelta(days=21)
        requests = self.env[MODEL_TEST_REQUEST]
        before = order.committed_date

        order.expected_collection_date = pickup

        committed, turnaround = order.committed_date, requests._date_after_working_days(pickup, 5)
        assert isinstance(committed, date)
        assert isinstance(before, date)
        assert isinstance(turnaround, date)
        self.assertGreaterEqual(committed, turnaround)
        self.assertLess(before, committed)

    def test_a_requested_date_before_the_pickup_estimate_is_not_copied(self):
        # Picked up today the samples would meet the requested date; picked up in three weeks they would not.
        order = self.make_quotable_order()
        requests = self.env[MODEL_TEST_REQUEST]
        order.requested_date = requests._date_after_working_days(date.today() + timedelta(days=1), 5)
        order.expected_collection_date = date.today() + timedelta(days=21)

        self.dialog(order).save().action_send()

        committed, requested = order.committed_date, order.requested_date
        assert isinstance(committed, date)
        assert isinstance(requested, date)
        self.assertGreater(committed, requested)

    def test_a_past_pickup_day_is_refused(self):
        order = self.make_quotable_order()
        order.expected_collection_date = date.today() - timedelta(days=1)

        with self.assertRaisesRegex(UserError, "pickup day"):
            self.dialog(order).save().action_send()
        self.assertFalse(order.quotation_ids)

    def test_the_collection_appointment_starts_on_the_pickup_day(self):
        order = self.make_quotable_order()
        pickup = date.today() + timedelta(days=3)
        order.expected_collection_date = pickup
        self.dialog(order).save().action_send()

        start = (
            self.env[MODEL_SAMPLE_COLLECTION_START]
            .with_user(self.sales)
            .with_context(default_order_id=order.id)
            .default_get(["appointment"])
        )

        self.assertEqual(self.env[MODEL_SAMPLE_TEST]._local_day(start["appointment"]), pickup)

    def test_sales_can_update_the_recipient_contact_and_send(self):
        order = self.make_quotable_order()

        form = self.dialog(order)
        form.partner_email = "updated@example.com"
        form.partner_phone = "0909123456"
        form.save().action_send()

        self.assertEqual(order.partner_id.email, "updated@example.com")
        self.assertEqual(order.partner_id.phone, "0909123456")
        self.assertEqual(order._latest_quotation().status, "sent")

    def test_a_percentage_or_a_fixed_amount_comes_off_the_whole_quotation(self):
        order = self.make_quotable_order()
        untaxed = order.amount_untaxed
        form = self.dialog(order)
        form.discount_type = "percentage"
        form.discount_percentage = 10
        form.save().action_apply_discount()
        self.assertAlmostEqual(order.amount_untaxed, untaxed * 0.9)
        discounted = order.amount_untaxed

        form = self.dialog(order)
        form.discount_type = "amount"
        form.discount_amount = 1000
        form.save().action_apply_discount()
        self.assertLess(order.amount_untaxed, discounted)

    def test_a_discount_out_of_range_is_refused(self):
        order = self.make_quotable_order()
        for discount_type, field, value, message in (
            ("percentage", "discount_percentage", 120, "between 0 and 100"),
            ("amount", "discount_amount", order.amount_untaxed + 1, "at most the untaxed total"),
        ):
            with self.subTest(discount_type=discount_type):
                form = self.dialog(order)
                form.discount_type = discount_type
                setattr(form, field, value)
                with self.assertRaisesRegex(UserError, message):
                    form.save().action_apply_discount()

    def test_changing_the_advance_clears_its_value(self):
        form = self.dialog(self.make_quotable_order())
        form.advance_mode = "percentage"
        form.advance_value = 30

        form.advance_mode = "fixed"

        self.assertEqual(form.advance_value, 0)

    def test_the_preview_prints_the_quotation(self):
        order = self.make_quotable_order()

        action = self.dialog(order).save().action_preview()

        self.assertEqual(action["type"], "ir.actions.report")

    def test_a_past_payment_deadline_is_refused(self):
        order = self.make_quotable_order()
        form = self.dialog(order)
        form.payment_deadline = fields.Datetime.now() - timedelta(hours=1)

        with self.assertRaisesRegex(UserError, "payment deadline"):
            form.save().action_send()
        self.assertFalse(order.quotation_ids)
