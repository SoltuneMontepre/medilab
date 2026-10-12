from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_ORDER_REJECT
from odoo.addons.sol_laboratory.constants.models import MODEL_SIGNATURE


@tagged("post_install", "-at_install")
class TestOrderApproval(OrderCase):
    def requested_order(self):
        order = self.make_confirmed_order()
        order.with_user(self.sales).action_request_approval()
        return order

    def approved_order(self):
        order = self.requested_order()
        order.with_user(self.head).action_sign()
        return order

    def test_requesting_signs_the_first_level(self):
        order = self.make_confirmed_order()
        self.assertEqual(order.approval_status, "none")

        order.with_user(self.sales).action_request_approval()

        self.assertEqual(order.approval_status, "requested")
        signature = self.env[MODEL_SIGNATURE].search(
            [("document_model", "=", "sale.order"), ("document_id", "=", order.id)]
        )
        self.assertEqual(signature.signer_id, self.sales_person)
        self.assertEqual(order._approval_requester(), self.sales_person)
        with self.assertRaises(UserError):
            order.with_user(self.sales).action_request_approval()

    def test_only_a_confirmed_order_is_signed(self):
        order = self.make_quotable_order()

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_request_approval()

        self.assertEqual(order.approval_status, "none")

    def test_the_head_of_sales_signing_the_last_level_approves(self):
        order = self.approved_order()

        self.assertEqual(order.approval_status, "approved")

    def test_the_salesperson_cannot_approve_their_own_order(self):
        order = self.requested_order()
        self.sales_person.role_ids |= self.head_person.role_ids

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_sign()

        self.assertEqual(order.approval_status, "requested")

    def test_a_rejection_tells_the_salesperson_the_reason(self):
        order = self.requested_order()

        order.with_user(self.head).action_reject("The price is below the cost of the tests")

        self.assertEqual(order.approval_status, "rejected")
        notices = order.message_ids.filtered(lambda message: "below the cost" in (message.body or ""))
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices.partner_ids, self.sales.partner_id)
        with self.assertRaises(UserError):
            order.with_user(self.head).action_sign()

    def test_the_rejection_wizard_needs_a_reason_and_rejects(self):
        order = self.requested_order()
        wizard = (
            self.env[MODEL_ORDER_REJECT].with_user(self.head).create({"order_id": order.id, "reason": "Wrong price"})
        )

        wizard.action_reject()

        self.assertEqual(order.approval_status, "rejected")
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.env[MODEL_ORDER_REJECT].create({"order_id": order.id, "reason": False})

    def test_an_advance_paid_on_a_signed_order_is_not_blocked(self):
        order = self.make_quotable_order()
        order.with_user(self.sales).action_send_quotation()
        self.pay_advance(order)
        order.with_user(self.sales).action_confirm_order()
        order.with_user(self.sales).action_request_approval()

        self.assertEqual(order.approval_status, "requested")
        self.assertTrue(order.sudo().order_line.filtered("is_downpayment"))

    def test_the_first_level_cannot_reject(self):
        order = self.make_confirmed_order()

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_reject("No")

    def test_signed_content_cannot_be_written_even_by_the_superuser(self):
        order = self.requested_order()
        line = order._catalog_lines()
        changes = (
            {"customer_id": self.contact.id},
            {"partner_id": self.other_person.work_contact_id.id},
            {"payment_deadline": fields.Datetime.now() + timedelta(days=9)},
            {"validity_date": fields.Date.today() + timedelta(days=9)},
        )

        for values in changes:
            with self.subTest(values=values), self.assertRaises(UserError):
                order.write(values)
        for values in (
            {"price_unit": 1},
            {"product_uom_qty": 5},
            {"discount": 10},
            {"tax_ids": False},
            {"sample_id": False},
        ):
            with self.subTest(values=values), self.assertRaises(UserError):
                line.write(values)
        with self.assertRaises(UserError):
            line.unlink()
        with self.assertRaises(UserError):
            self.env["sale.order.line"].create(
                {"order_id": order.id, "product_id": self.lead_product.product_variant_ids.id}
            )

        order.write({"expected_result_date": fields.Date.today()})

    def test_sample_collection_waits_for_the_approval(self):
        order = self.requested_order()

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_start_sample_collection()
        order.with_user(self.head).action_sign()

        self.assertTrue(order.with_user(self.sales).action_start_sample_collection())

    def test_withdrawing_every_signature_edits_the_order_again_in_a_new_version(self):
        order = self.approved_order()
        version = order.document_version

        with self.assertRaises(UserError):
            order.with_user(self.sales).action_withdraw()
        order.with_user(self.head).action_withdraw()
        self.assertEqual(order.approval_status, "requested")
        self.assertEqual(order.document_version, version)
        order.with_user(self.sales).action_withdraw()

        self.assertEqual(order.approval_status, "none")
        self.assertGreater(order.document_version, version)
        deadline = fields.Datetime.now() + timedelta(days=9)
        order.write({"payment_deadline": deadline})
        order._catalog_lines().write({"product_uom_qty": 3})
        self.assertEqual(order.payment_deadline, deadline)

    def test_a_completed_order_keeps_its_signatures(self):
        order = self.approved_order()
        order._set_status("completed")

        with self.assertRaises(UserError):
            order.with_user(self.head).action_withdraw()

        self.assertEqual(order.approval_status, "approved")
