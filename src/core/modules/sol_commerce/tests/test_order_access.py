from lxml import etree

from odoo.exceptions import AccessError, UserError
from odoo.fields import Command
from odoo.tests import new_test_user, tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_SALE_ORDER, MODEL_SALE_REPORT


@tagged("post_install", "-at_install")
class TestOrderAccess(OrderCase):
    def test_claim_is_once_and_the_queue_is_oldest_first(self):
        older = self.make_order([(self.lead_product, 1)], status="submitted")
        newer = self.make_order([(self.package_product, 1)], status="submitted")
        older.submitted_at = "2026-01-01 08:00:00"
        newer.submitted_at = "2026-01-02 08:00:00"
        orders = self.env[MODEL_SALE_ORDER]

        queued = orders.with_user(self.other_sales).search(
            [("id", "in", (older | newer).ids)], order="submitted_at, id"
        )
        self.assertEqual(list(queued), [older, newer])

        older.with_user(self.sales).action_claim()
        with self.assertRaises(UserError):
            older.with_user(self.sales).action_claim()
        with self.assertRaises(AccessError):
            older.with_user(self.other_sales).read(["name"])

        self.assertFalse(orders.with_user(self.other_sales).search([("id", "=", older.id)]))
        self.assertEqual(older.with_user(self.head).user_id, self.sales)
        self.assertIn(newer, orders.with_user(self.other_sales).search([("order_status", "=", "submitted")]))

    def test_a_draft_is_not_in_the_queue(self):
        draft = self.make_order([(self.lead_product, 1)])

        self.assertFalse(self.env[MODEL_SALE_ORDER].with_user(self.sales).search([("id", "=", draft.id)]))
        self.assertEqual(draft.with_user(self.head).order_status, "draft")

    def test_a_salesperson_opens_an_order_that_has_invoices(self):
        order = self.make_confirmed_order()
        self.env.invalidate_all()
        orders = self.env[MODEL_SALE_ORDER].with_user(self.sales)
        form_fields = orders.get_views([(False, "form")])["models"][MODEL_SALE_ORDER]["fields"]

        [values] = orders.browse(order.id).web_read({name: {} for name in form_fields})

        self.assertEqual((values["invoice_count"], values["payment_status"]), (1, "paid"))

    def test_the_invoices_button_is_for_those_who_read_invoices(self):
        orders = self.env[MODEL_SALE_ORDER]
        invoicing = new_test_user(
            self.env, login="order.invoicing", groups="base.group_user,account.group_account_invoice"
        )

        def invoices_buttons(user):
            arch = etree.fromstring(orders.with_user(user).get_view(view_type="form")["arch"])
            return arch.xpath("//button[@name='action_view_invoice']")

        self.assertFalse(invoices_buttons(self.sales))
        self.assertTrue(invoices_buttons(invoicing))

    def test_a_salesperson_analyses_only_their_own_orders(self):
        mine = self.make_confirmed_order()
        theirs = self.make_confirmed_order()
        theirs.user_id = self.other_sales
        self.env.flush_all()
        names = (mine | theirs).mapped("name")
        reports = self.env[MODEL_SALE_REPORT]

        def analysed(user):
            return {name for [name] in reports.with_user(user)._read_group([("name", "in", names)], ["name"])}

        self.assertEqual(analysed(self.sales), {mine.name})
        self.assertEqual(analysed(self.other_sales), {theirs.name})
        self.assertEqual(analysed(self.head), set(names))
        for user in (self.sales, self.other_sales):
            dashboard = self.env[MODEL_SALE_ORDER].with_user(user).retrieve_sale_dashboard(30)
            self.assertEqual(dashboard["orders"]["total"], 1)

    def test_sales_creates_an_order_for_a_customer(self):
        order = (
            self.env[MODEL_SALE_ORDER]
            .with_user(self.sales)
            .with_context(medilab_sales_order=True)
            .create(
                {
                    "partner_id": self.contact.id,
                    "customer_id": self.customer.id,
                    "order_line": [
                        Command.create({"product_id": self.lead_product.product_variant_ids.id, "product_uom_qty": 1})
                    ],
                }
            )
        )

        self.assertEqual((order.source, order.order_status, order.user_id), ("sales", "claimed", self.sales))
        self.assertEqual(order.order_line.price_unit, self.lead_product.list_price)

    def test_a_new_order_keeps_its_salesperson_when_the_contact_is_chosen(self):
        orders = self.env[MODEL_SALE_ORDER].with_user(self.sales)

        on_screen = orders.with_context(medilab_sales_order=True).new({"partner_id": self.contact.id})
        elsewhere = orders.new({"partner_id": self.contact.id})

        self.assertEqual(on_screen.user_id, self.sales)
        self.assertFalse(elsewhere.user_id)
