from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_QUOTATION


@tagged("post_install", "-at_install")
class TestQuotationAdvance(OrderCase):
    def as_customer(self, order):
        """The latest quotation as the customer's portal user reaches it on the portal."""
        return order._latest_quotation().with_user(self.portal).sudo()

    def customer_notices(self, order):
        return order.message_ids.filtered(
            lambda message: message.message_type == "comment" and message.partner_ids == self.contact
        )

    def test_sending_with_an_advance_creates_one_invoice_and_one_customer_notice(self):
        order = self.make_quotable_order()
        total = order.amount_total

        order.with_user(self.sales).action_send_quotation()

        invoice = order.sudo().invoice_ids
        self.assertEqual(len(invoice), 1)
        self.assertEqual(invoice.state, "posted")
        self.assertEqual(invoice.move_type, "out_invoice")
        self.assertTrue(invoice.line_ids.sale_line_ids.filtered("is_downpayment"))
        self.assertEqual(invoice.amount_total, total)
        notices = self.customer_notices(order)
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices.attachment_ids, order._latest_quotation().attachment_id)
        self.assertEqual(order.order_status, "claimed")

    def test_the_advance_follows_the_percentage_and_the_fixed_amount(self):
        percentage = self.make_quotable_order()
        percentage.write({"advance_mode": "percentage", "advance_value": 30})
        fixed = self.make_quotable_order()
        fixed.write({"advance_mode": "fixed", "advance_value": 50000})

        percentage.with_user(self.sales).action_send_quotation()
        fixed.with_user(self.sales).action_send_quotation()

        self.assertAlmostEqual(percentage.sudo().invoice_ids.amount_total, percentage.amount_total * 0.3)
        self.assertAlmostEqual(fixed.sudo().invoice_ids.amount_total, 50000)

    def test_an_advance_needs_a_method_and_a_value(self):
        order = self.make_quotable_order()
        order.advance_method = False
        with self.assertRaises(UserError):
            order.with_user(self.sales).action_send_quotation()
        order.write({"advance_method": "cash", "advance_mode": "percentage", "advance_value": 0})
        with self.assertRaises(UserError):
            order.with_user(self.sales).action_send_quotation()
        order.advance_value = 101
        with self.assertRaises(UserError):
            order.with_user(self.sales).action_send_quotation()

        self.assertFalse(order.quotation_ids)
        self.assertFalse(order.sudo().invoice_ids)

    def test_sending_a_second_time_does_not_create_a_second_invoice(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_send_quotation()

        self.assertEqual(len(order.sudo().invoice_ids), 1)
        self.assertEqual(len(self.customer_notices(order)), 1)

    def test_only_the_head_of_sales_sends_without_an_advance(self):
        order = self.make_quotable_order()
        order.advance_method = "none"

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_send_quotation()
        self.assertFalse(order.quotation_ids)

        order.with_user(self.head).action_send_quotation()

        self.assertEqual(order._latest_quotation().status, "sent")
        self.assertFalse(order.sudo().invoice_ids)
        self.assertEqual(len(self.customer_notices(order)), 1)

    def test_paying_the_advance_accepts_the_quotation(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        self.assertEqual(order.quotation_follow_up, "unpaid")

        self.pay_advance(order)

        self.assertEqual(order._latest_quotation().status, "accepted")
        self.assertEqual(order.quotation_follow_up, "paid")
        self.assertFalse(order.show_unpaid_warning)

    def test_the_customer_accepts_a_quotation_sent_without_an_advance(self):
        order = self.make_quotable_order()
        order.advance_method = "none"
        order.with_user(self.head).action_send_quotation()

        self.as_customer(order).action_accept()

        self.assertEqual(order._latest_quotation().status, "accepted")
        self.assertEqual(order.quotation_follow_up, "paid")
        self.assertTrue(order.show_unpaid_warning)

    def test_only_a_quotation_without_an_advance_is_accepted_by_the_customer(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()

        with self.assertRaises(UserError):
            self.as_customer(order).action_accept()

        self.assertEqual(order._latest_quotation().status, "sent")

    def test_a_salesperson_cannot_accept_for_the_customer(self):
        order = self.make_quotable_order()
        order.advance_method = "none"
        order.with_user(self.head).action_send_quotation()
        quotation = order._latest_quotation()

        for caller in (quotation.with_user(self.sales), quotation.with_user(self.head), quotation):
            with self.assertRaises(AccessError):
                caller.action_accept()

        self.assertEqual(quotation.status, "sent")

    def test_paying_the_invoice_of_a_replaced_revision_does_not_accept_the_new_one(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        first = order._latest_quotation()
        old_invoice = first.advance_invoice_id
        order.with_user(self.sales).action_revise_quotation()
        order.with_user(self.sales).action_send_quotation()
        second = order._latest_quotation()

        old_invoice._invoice_paid_hook()

        self.assertEqual(old_invoice.state, "cancel")
        self.assertEqual(second.advance_invoice_id.state, "posted")
        self.assertNotEqual(second.advance_invoice_id, old_invoice)
        self.assertEqual(second.status, "sent")
        self.assertEqual(first.status, "replaced")
        self.pay_advance(order)
        self.assertEqual(second.status, "accepted")

    def test_paying_after_the_quotation_expired_does_not_accept_it(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        order.payment_deadline = fields.Datetime.now() - timedelta(days=1)
        self.env[MODEL_QUOTATION]._flag_expired()

        self.pay_advance(order)

        self.assertEqual(order._latest_quotation().status, "expired")
        self.assertEqual(order.quotation_follow_up, "expired")

    def test_extending_the_deadline_accepts_an_expired_quotation_whose_advance_was_paid(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        order.payment_deadline = fields.Datetime.now() - timedelta(days=1)
        self.env[MODEL_QUOTATION]._flag_expired()
        self.pay_advance(order)
        self.assertEqual(order._latest_quotation().status, "expired")

        order.payment_deadline = fields.Datetime.now() + timedelta(days=3)

        self.assertEqual(order._latest_quotation().status, "accepted")
        self.assertEqual(order.quotation_follow_up, "paid")

    def test_extending_the_deadline_keeps_an_unpaid_expired_quotation_sent(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        order.payment_deadline = fields.Datetime.now() - timedelta(days=1)
        self.env[MODEL_QUOTATION]._flag_expired()

        order.payment_deadline = fields.Datetime.now() + timedelta(days=3)

        self.assertEqual(order._latest_quotation().status, "sent")

    def test_paying_the_old_advance_during_a_revision_does_not_accept_the_quotation(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        quotation = order._latest_quotation()
        invoice = quotation.advance_invoice_id
        order.with_user(self.sales).action_revise_quotation()
        self.assertEqual(invoice.state, "cancel")

        invoice._invoice_paid_hook()

        self.assertEqual(quotation.status, "sent")
        with self.assertRaises(UserError):
            order.with_user(self.sales).action_confirm_order()
        quotation.write({"status": "accepted"})
        with self.assertRaises(UserError):
            order.with_user(self.sales).action_confirm_order()
        self.assertFalse(order.test_request_id)

    def test_a_quotation_whose_advance_was_paid_cannot_be_revised(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        self.pay_advance(order)
        order._latest_quotation().write({"status": "sent"})

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_revise_quotation()

        self.assertEqual(order.state, "sent")
        self.assertEqual(order._latest_quotation().advance_invoice_id.state, "posted")

    def test_follow_up_shows_unpaid_paid_declined_and_expired(self):
        unpaid, paid, declined, expired = (self.make_quotable_order() for _ in range(4))
        for order in (unpaid, paid, declined, expired):
            order.with_user(self.sales).action_send_quotation()
        self.pay_advance(paid)
        declined._latest_quotation().action_decline("Too expensive")
        expired.payment_deadline = fields.Datetime.now() - timedelta(days=1)
        self.env[MODEL_QUOTATION]._flag_expired()

        self.assertEqual(
            [order.quotation_follow_up for order in (unpaid, paid, declined, expired)],
            ["unpaid", "paid", "declined", "expired"],
        )

    def test_the_company_does_not_ask_the_customer_to_sign_online(self):
        self.assertFalse(self.env.company.portal_confirmation_sign)
        self.assertFalse(self.make_order([(self.lead_product, 1)]).require_signature)

    def test_a_salesperson_cannot_switch_a_sent_advance_quotation_to_no_advance(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()

        with self.assertRaises(UserError):
            order.with_user(self.sales).write({"advance_method": "none"})

        self.assertEqual(order.advance_method, "cash")
        with self.assertRaises(UserError):
            self.as_customer(order).action_accept()
        self.assertEqual(order._latest_quotation().status, "sent")

    def test_a_quotation_being_revised_cannot_be_accepted(self):
        order = self.make_quotable_order()
        order.advance_method = "none"
        order.with_user(self.head).action_send_quotation()
        order.with_user(self.sales).action_revise_quotation()
        self.assertEqual(order.state, "draft")

        with self.assertRaises(UserError):
            self.as_customer(order).action_accept()

        self.assertEqual(order._latest_quotation().status, "sent")

    def test_accepting_follows_the_advance_invoice_of_the_quotation(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        order.with_user(self.sales).action_revise_quotation()
        order.with_user(self.sales).write({"advance_method": "none"})
        quotation = order._latest_quotation()
        self.assertTrue(quotation.advance_invoice_id)

        with self.assertRaises(UserError):
            self.as_customer(order).action_accept()

        self.assertEqual(quotation.status, "sent")

    def test_the_advance_cannot_change_after_sending_until_the_quotation_is_revised(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()

        for values in ({"advance_method": "none"}, {"advance_mode": "fixed"}, {"advance_value": 5}):
            with self.subTest(values=values):
                with self.assertRaises(UserError):
                    order.write(values)
                with self.assertRaises(UserError):
                    order.with_user(self.sales).write(values)
        self.assertEqual(order.advance_method, "cash")
        with self.assertRaises(UserError):
            self.as_customer(order).action_accept()

        order.with_user(self.sales).action_revise_quotation()
        order.with_user(self.sales).write({"advance_method": "bank_transfer"})

        self.assertEqual(order.advance_method, "bank_transfer")
