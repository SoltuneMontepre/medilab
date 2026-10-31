from lxml import etree

from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER
from odoo.addons.sol_laboratory.constants.models import MODEL_PERMISSION
from odoo.addons.sol_laboratory.services.record_id import persisted_id


@tagged("post_install", "-at_install")
class TestOrderReadScope(OrderCase):
    """A salesperson who reads every order opens another salesperson's order read-only."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        read_all = cls.env[MODEL_PERMISSION].search([("code", "=", "order.read.all")])
        cls.other_person.permission_ids = [Command.link(persisted_id(read_all))]

    def test_without_read_all_another_salespersons_order_cannot_be_opened(self):
        order = self.make_quotable_order()
        self.other_person.permission_ids = self.other_person.permission_ids.filtered(
            lambda permission: permission.code != "order.read.all"
        )

        with self.assertRaises(AccessError):
            order.with_user(self.other_sales).read(["name"])

    def test_read_all_opens_another_salespersons_order_read_only(self):
        order = self.make_quotable_order()
        opened = order.with_user(self.other_sales)

        self.assertEqual(opened.name, order.name)
        self.assertTrue(opened.sample_ids)
        self.assertFalse(opened.order_can_edit)
        self.assertTrue(order.with_user(self.sales).order_can_edit)
        with self.assertRaises(AccessError):
            opened.write({"note": "Changed by another salesperson"})

    def test_a_reader_cannot_act_on_the_order(self):
        order = self.make_quotable_order()
        opened = order.with_user(self.other_sales)

        with self.assertRaises(AccessError):
            opened.action_send_quotation()
        with self.assertRaises(AccessError):
            opened.action_sales_cancel()
        with self.assertRaises(AccessError):
            opened.sample_ids.write({"customer_sample_name": "Changed sample"})
        self.assertEqual(order.order_status, "claimed")

    def test_a_reader_cannot_request_or_sign_the_approval(self):
        order = self.make_confirmed_order()
        opened = order.with_user(self.other_sales)

        self.assertFalse(opened.approval_can_sign)
        with self.assertRaises(AccessError):
            opened.action_request_approval()
        self.assertEqual(order.approval_status, "none")

    def _nodes(self, path):
        arch = etree.fromstring(self.env[MODEL_SALE_ORDER].get_view(view_type="form")["arch"])
        found = arch.xpath(path)
        assert isinstance(found, list)
        return [node for node in found if isinstance(node, etree._Element)]

    def test_the_form_is_locked_for_readers(self):
        for button in self._nodes("//header/button[@name='action_send_quotation' or @name='action_sales_cancel']"):
            with self.subTest(button=button.get("name")):
                self.assertIn("not order_can_edit", button.get("invisible") or "")
        claim = self._nodes("//header/button[@name='action_claim']")[0]
        self.assertNotIn("order_can_edit", claim.get("invisible") or "")
        customer = self._nodes("//sheet//field[@name='customer_id']")[0]
        self.assertIn("not order_can_edit", customer.get("readonly") or "")

    def test_the_head_of_sales_edits_every_order(self):
        order = self.make_quotable_order()

        self.assertTrue(order.with_user(self.head).order_can_edit)
        order.with_user(self.head).write({"note": "Checked by the Head of Sales"})

    def test_claiming_needs_an_edit_permission(self):
        queued = self.make_order([(self.lead_product, 1)], status="submitted")
        self.other_person.permission_ids = self.other_person.permission_ids.filtered(
            lambda permission: permission.action != "edit" or permission.document_model != MODEL_SALE_ORDER
        )

        with self.assertRaises(AccessError):
            queued.with_user(self.other_sales).action_claim()
        queued.with_user(self.sales).action_claim()
        self.assertEqual(queued.user_id, self.sales)

    def test_sales_puts_an_order_in_the_queue_with_catalog_prices(self):
        queued = (
            self.env[MODEL_SALE_ORDER]
            .with_user(self.sales)
            .create(
                {
                    "customer_id": self.customer.id,
                    "partner_id": self.contact.id,
                    "source": "portal",
                    "order_status": "submitted",
                    "order_line": [Command.create({"product_id": self.lead_product.product_variant_id.id})],
                }
            )
        )

        self.assertFalse(queued.user_id)
        self.assertEqual(queued.order_line.price_unit, self.lead_product.list_price)
