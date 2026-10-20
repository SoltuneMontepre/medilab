from odoo.tests import Form, tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_laboratory.constants.models import MODEL_CUSTOMER


@tagged("post_install", "-at_install")
class TestCustomerOrders(OrderCase):
    """The status a customer sees, the order's contact, and orders kept through a merge."""

    def test_the_customer_sees_draft_submitted_quoted_then_the_laboratory_status(self):
        draft = self.make_order([(self.lead_product, 1)])
        submitted = self.make_order([(self.lead_product, 1)], status="submitted")
        quoted = self.make_quotable_order()
        quoted.with_user(self.sales).action_send_quotation()
        confirmed = self.make_confirmed_order()
        cancelled = self.make_order([(self.lead_product, 1)])
        cancelled.action_customer_cancel()

        self.assertEqual(
            [order.customer_status for order in (draft, submitted, quoted, confirmed, cancelled)],
            ["draft", "submitted", "quoted", "waiting", "cancelled"],
        )
        for request_status, shown in (
            ("testing", "testing"),
            ("awaiting_approval", "testing"),
            ("reported", "completed"),
        ):
            confirmed.test_request_id.sudo().write({"status": request_status})
            confirmed.invalidate_recordset(["customer_status"])
            self.assertEqual(confirmed.customer_status, shown)

    def test_choosing_the_customer_preselects_its_default_contact(self):
        lan = self.env["res.partner"].create({"name": "Ngo Thi Lan", "parent_id": self.customer.id})
        self.customer_record.default_contact_id = lan

        with Form(self.env[MODEL_SALE_ORDER].with_context(medilab_sales_order=True)) as order:
            order.customer_id = self.customer
            self.assertEqual(order.partner_id, lan)

    def test_merging_moves_the_orders_to_the_matched_customer(self):
        registered = self.env["res.partner"].create({"name": "Cong ty Nuoc Sach (registered)", "vat": "0315678901"})
        person = self.env["res.partner"].create({"name": "Do Van Tai", "parent_id": registered.id})
        duplicate = self.env[MODEL_CUSTOMER].create(
            {"partner_id": registered.id, "duplicate_of_id": self.customer_record.id}
        )
        order = self.make_order([(self.lead_product, 1)], customer_id=registered.id, partner_id=person.id)

        duplicate.action_merge_duplicate()

        self.assertEqual((order.customer_id, order.partner_id.parent_id), (self.customer, self.customer))
        self.assertFalse(registered.exists())
