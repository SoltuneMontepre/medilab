from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_CUSTOMER_SALES_TERMS
from odoo.addons.sol_laboratory.constants.models import MODEL_TEST_REQUEST


@tagged("post_install", "-at_install")
class TestOrderConfirmation(OrderCase):
    def accepted_unpaid_order(self, lines=None):
        order = self.make_quotable_order(lines)
        order.advance_method = "none"
        order.with_user(self.head).action_send_quotation()
        order._latest_quotation()._accept()
        order.with_user(self.sales).action_confirm_order()
        return order

    def test_confirming_creates_the_test_request_from_the_samples(self):
        order = self.make_quotable_order([(self.lead_product, 2), (self.package_product, 1)])
        samples = order.sample_ids
        order.with_user(self.sales).action_send_quotation()
        self.pay_advance(order)

        order.with_user(self.sales).action_confirm_order()

        request = order.test_request_id
        self.assertEqual(order.order_status, "confirmed")
        self.assertEqual(request.customer_id, self.customer_record)
        self.assertEqual(request.report_recipient_id, self.contact)
        self.assertEqual(len(request.sample_ids), len(samples))
        tests = request.sample_ids.test_ids
        self.assertEqual(
            sorted(test.parameter_id.id for test in tests), sorted([self.parameter.id] * 2 + [self.other.id])
        )
        self.assertEqual(sum(tests.filtered(lambda test: test.parameter_id == self.parameter).mapped("quantity")), 3)
        self.assertEqual(request.sample_ids.customer_sample_name, samples.customer_sample_name)

    def test_a_quotation_must_be_accepted_before_confirming(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_confirm_order()

        self.assertEqual(order.order_status, "claimed")
        self.assertFalse(order.test_request_id)

    def test_an_order_without_a_quotation_cannot_be_confirmed(self):
        order = self.make_quotable_order()

        with self.assertRaises(UserError) as error:
            order.with_user(self.sales).action_confirm_order()

        self.assertIn("accept the quotation", str(error.exception))

    def test_a_replaced_revision_cannot_be_confirmed(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        first = order._latest_quotation()
        order.with_user(self.sales).action_revise_quotation()
        order.with_user(self.sales).action_send_quotation()
        self.assertEqual(first.status, "replaced")

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_confirm_order()

        self.assertEqual(order.order_status, "claimed")
        self.assertFalse(order.test_request_id)

    def test_the_standard_confirm_button_runs_the_same_checks(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_confirm()
        self.pay_advance(order)
        order.with_user(self.sales).action_confirm()

        self.assertEqual(order.order_status, "confirmed")
        self.assertEqual(order.state, "sale")
        self.assertTrue(order.test_request_id)

    def test_the_confirm_context_key_cannot_skip_the_checks(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()

        for context in ({"medilab_odoo_confirm": True}, {"medilab_confirming_order_ids": [order.id]}):
            with self.assertRaises(UserError):
                order.with_user(self.sales).with_context(**context).action_confirm()

        self.assertEqual(order.order_status, "claimed")
        self.assertEqual(order.state, "sent")
        self.assertFalse(order.test_request_id)

    def test_an_order_is_confirmed_once(self):
        order = self.make_confirmed_order()

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_confirm_order()

    def test_confirming_without_payment_goes_on_and_warns(self):
        order = self.accepted_unpaid_order()

        self.assertEqual(order.order_status, "confirmed")
        self.assertTrue(order.test_request_id)
        self.assertTrue(order.show_unpaid_warning)

    def test_confirming_needs_the_customer_record(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        self.pay_advance(order)
        order.customer_id = self.env["res.partner"].create({"name": "Cong ty chua la khach hang"})

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_confirm_order()

        self.assertEqual(order.order_status, "claimed")

    def test_credit_blocks_the_request_of_an_unpaid_order_unless_the_customer_may_buy_on_credit(self):
        order = self.accepted_unpaid_order()
        request = order.test_request_id
        self.assertTrue(request._credit_blocks_confirmation())
        with self.assertRaises(UserError):
            request.action_confirm()

        terms = (
            self.env[MODEL_CUSTOMER_SALES_TERMS]
            .with_user(self.head)
            .create({"customer_id": self.customer_record.id, "allow_credit": True})
        )

        self.assertFalse(request._credit_blocks_confirmation())
        terms.with_user(self.head).allow_credit = False
        self.assertTrue(request._credit_blocks_confirmation())

    def test_a_paid_order_and_a_request_without_an_order_are_not_blocked(self):
        paid = self.make_confirmed_order()
        alone = self.env[MODEL_TEST_REQUEST].create({"customer_id": self.customer_record.id})

        self.assertFalse(paid.test_request_id._credit_blocks_confirmation())
        self.assertFalse(alone._credit_blocks_confirmation())

    def test_the_request_of_a_paid_order_goes_through_the_paid_step(self):
        request = self.make_confirmed_order().test_request_id

        request.action_confirm()

        self.assertEqual(request.status, "paid")
        request.sample_ids[:1].with_user(self.sales).sudo().action_receive(1, "damaged", "The bottle leaked")
        self.assertEqual(request.status, "sample_received")

    def test_the_request_of_a_credit_customer_is_paid_on_confirmation(self):
        request = self.accepted_unpaid_order().test_request_id
        self.env[MODEL_CUSTOMER_SALES_TERMS].create({"customer_id": self.customer_record.id, "allow_credit": True})

        request.action_confirm()

        self.assertEqual(request.status, "paid")

    def test_only_the_request_of_an_order_awaits_payment(self):
        request = self.make_confirmed_order().test_request_id
        alone = self.env[MODEL_TEST_REQUEST].create({"customer_id": self.customer_record.id})

        self.assertTrue(request._awaits_payment())
        self.assertFalse(alone._awaits_payment())

    def test_only_the_head_of_sales_changes_the_sales_terms(self):
        terms = self.env[MODEL_CUSTOMER_SALES_TERMS]

        with self.assertRaises(AccessError):
            terms.with_user(self.sales).create({"customer_id": self.customer_record.id, "allow_credit": True})
        created = terms.with_user(self.head).create({"customer_id": self.customer_record.id})
        with self.assertRaises(AccessError):
            created.with_user(self.sales).allow_credit = True

        created.with_user(self.head).allow_credit = True

        self.assertTrue(created.allow_credit)
        self.assertFalse(created.search([("customer_id", "=", self.customer_record.id), ("allow_credit", "=", False)]))
