from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER_LINE
from odoo.addons.sol_laboratory.constants.models import MODEL_SAMPLE_TYPE


@tagged("post_install", "-at_install")
class TestOrderFreeze(OrderCase):
    """From confirmation, what the customer and sales agreed on the order no longer changes."""

    def test_confirmed_content_cannot_be_written_even_by_the_superuser(self):
        order = self.make_confirmed_order()
        line = order._catalog_lines()
        changes = (
            {"customer_id": self.contact.id},
            {"partner_id": self.other_person.work_contact_id.id},
            {"payment_deadline": fields.Datetime.now() + timedelta(days=9)},
            {"validity_date": fields.Date.today() + timedelta(days=9)},
            {"test_request_id": False},
        )

        for values in changes:
            with self.subTest(values=values), self.assertRaises(UserError):
                order.write(values)
        for values in (
            {"price_unit": 1},
            {"product_uom_qty": 5},
            {"product_uom_id": line.product_uom_id.id},
            {"discount": 10},
            {"tax_ids": False},
            {"sample_id": False},
            {"linked_line_id": line.id},
            {"order_id": self.make_quotable_order().id},
        ):
            with self.subTest(values=values), self.assertRaises(UserError):
                line.write(values)
        with self.assertRaises(UserError):
            line.unlink()
        draft_line = self.make_quotable_order()._catalog_lines()
        with self.assertRaises(UserError):
            draft_line.write({"order_id": order.id})
        with self.assertRaises(UserError):
            self.env[MODEL_SALE_ORDER_LINE].create(
                {"order_id": order.id, "product_id": self.lead_product.product_variant_ids.id}
            )
        sample = order.sample_ids
        for values in (
            {"customer_sample_name": "Another sample"},
            {"sample_type_id": self.env[MODEL_SAMPLE_TYPE].create({"name": "Soil", "code": "LM-SOIL"}).id},
            {"physical_state": "solid"},
            {"regulation_id": False},
        ):
            with self.subTest(values=values), self.assertRaises(UserError):
                sample.write(values)
        with self.assertRaises(UserError):
            sample.unlink()
        with self.assertRaises(UserError):
            self.make_sample(order, "Second sample")

        order.write({"expected_result_date": fields.Date.today()})

    def test_a_confirmed_order_cannot_go_back_to_a_quotation_or_drop_a_line_as_a_down_payment(self):
        order = self.make_confirmed_order()

        for state in ("draft", "sent"):
            with self.subTest(state=state), self.assertRaises(UserError):
                order.write({"state": state})
        with self.assertRaises(UserError):
            order._catalog_lines().write({"is_downpayment": True})
        with self.assertRaises(UserError):
            order.sudo().order_line.filtered("is_downpayment").write({"is_downpayment": False})
        with self.assertRaises(UserError):
            order.with_context(medilab_status_change=True).write({"order_status": "claimed"})

    def test_a_completed_order_stays_frozen(self):
        order = self.make_confirmed_order()
        order._set_status("completed")

        with self.assertRaises(UserError):
            order.write({"validity_date": fields.Date.today() + timedelta(days=9)})

    def test_the_contact_of_an_order_not_confirmed_yet_can_change(self):
        order = self.make_quotable_order()

        order.write({"partner_id": self.customer.id, "validity_date": fields.Date.today() + timedelta(days=9)})

        self.assertEqual(order.partner_id, self.customer)
