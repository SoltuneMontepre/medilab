from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from .purchasing_case import PurchasingCase
from odoo.addons.sol_inventory.constants.models import MODEL_PURCHASE_ORDER_REJECT


@tagged("post_install", "-at_install")
class TestPurchaseOrders(PurchasingCase):
    def test_requesting_approval_signs_the_first_level_and_the_last_level_signs_it(self):
        order = self.make_order((self.acid, 2500, 1200), department_id=self.chemistry.id)
        self.assertEqual(order.approval_status, "none")

        order.action_request_approval()
        self.assertEqual(order.approval_status, "requested")
        self.assertEqual(order._approval_requester(), self.storekeeper)
        self.assertEqual(order._approval_department(), self.chemistry)

        order.with_user(self.signer).action_sign()
        self.assertEqual(order.approval_status, "approved")
        self.assertEqual(order.state, "draft")

    def test_an_order_cannot_be_sent_before_its_approval_chain_has_signed_it(self):
        order = self.make_order((self.gloves, 10, 50000))
        order.action_request_approval()

        for send in (order.action_send_to_supplier, order.button_confirm, order.button_approve, order.action_rfq_send):
            with self.assertRaises(UserError):
                send()
        order.with_context(mark_rfq_as_sent=True).message_post(body="Sent by hand")

        self.assertEqual(order.state, "draft")
        self.assertFalse(order.sudo().picking_ids)

    def test_sending_a_signed_order_confirms_it_and_opens_the_email_to_the_supplier(self):
        order = self.signed_order((self.gloves, 10, 50000))

        action = order.action_send_to_supplier()

        self.assertEqual(action["res_model"], "mail.compose.message")
        self.assertEqual(order.state, "purchase")
        receipt = order.sudo().picking_ids
        self.assertEqual(receipt.picking_type_code, "incoming")
        self.assertEqual(receipt.location_dest_id, self.central)
        self.assertEqual(order.receipt_status, "pending")

    def test_odoo_approval_of_large_orders_is_off(self):
        self.env.company.write({"po_double_validation": "two_step", "po_double_validation_amount": 0})
        order = self.signed_order((self.gloves, 10, 50000))

        order.action_send_to_supplier()

        self.assertEqual(order.state, "purchase")

    def test_a_signed_order_cannot_be_changed(self):
        order = self.make_order((self.gloves, 10, 50000))
        order.action_request_approval()

        with self.assertRaises(UserError):
            order.partner_id = self.env["res.partner"].create({"name": "Other Supplier"})
        with self.assertRaises(UserError):
            order.order_line.product_qty = 20
        with self.assertRaises(UserError):
            order.order_line = [Command.create({"product_id": self.plates.id, "product_qty": 5, "price_unit": 1000})]

        order.date_planned = "2026-11-30 08:00:00"

    def test_withdrawing_the_only_signature_reopens_the_order(self):
        order = self.make_order((self.gloves, 10, 50000))
        order.action_request_approval()

        order.action_withdraw()

        self.assertEqual(order.approval_status, "none")
        order.order_line.product_qty = 20
        self.assertEqual(order.order_line.product_qty, 20)

    def test_rejecting_needs_a_reason_and_tells_the_storekeeper(self):
        order = self.make_order((self.gloves, 10, 50000))
        order.action_request_approval()

        with self.assertRaises(UserError):
            order.with_user(self.signer).action_reject(" ")
        self.env[MODEL_PURCHASE_ORDER_REJECT].with_user(self.signer).create(
            {"order_id": order.id, "reason": "The supplier's price is above the last one"}
        ).action_reject()

        self.assertEqual(order.approval_status, "rejected")
        self.assertTrue(order.message_ids.filtered(lambda message: "above the last one" in (message.body or "")))

    def test_a_person_without_the_signing_role_cannot_sign(self):
        order = self.make_order((self.gloves, 10, 50000))
        order.action_request_approval()

        with self.assertRaises(UserError):
            order.action_sign()

        self.assertEqual(order.approval_status, "requested")

    def test_a_signed_order_is_cancelled_only_once_its_signatures_are_withdrawn(self):
        order = self.make_order((self.gloves, 10, 50000))
        order.action_request_approval()

        with self.assertRaises(UserError):
            order.button_cancel()

        order.action_withdraw()
        order.button_cancel()
        self.assertEqual(order.state, "cancel")

    def test_a_sent_order_is_cancelled_with_its_receipt_while_nothing_arrived(self):
        order = self.sent_order((self.gloves, 10, 50000))

        order.button_cancel()

        self.assertEqual(order.state, "cancel")
        self.assertEqual(order.sudo().picking_ids.state, "cancel")
        with self.assertRaises(UserError):
            order.button_draft()

    def test_a_sent_order_is_not_cancelled_once_goods_arrived(self):
        order = self.sent_order((self.gloves, 10, 50000))
        receipt = order.picking_ids.with_user(self.buyer)
        receipt.move_ids.quantity = 4
        receipt.button_validate()

        with self.assertRaises(UserError):
            order.button_cancel()

        self.assertEqual(order.state, "purchase")

    def test_a_signed_order_is_never_deleted(self):
        signed = self.signed_order((self.gloves, 10, 50000))
        unsigned = self.make_order((self.gloves, 5, 50000))

        with self.assertRaises(UserError):
            signed.unlink()

        unsigned.button_cancel()
        unsigned.unlink()
        self.assertFalse(unsigned.exists())

    def test_an_unfinished_order_keeps_its_department_in_use(self):
        department = self.env["hr.department"].create({"name": "Heavy metals"})
        order = self.make_order((self.gloves, 10, 50000), department_id=department.id)

        with self.assertRaises(UserError):
            department.action_archive()

        order.button_cancel()
        department.action_archive()
        self.assertFalse(department.active)
