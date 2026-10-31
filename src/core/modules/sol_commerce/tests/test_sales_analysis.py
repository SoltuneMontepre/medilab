from ast import literal_eval
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .order_case import OrderCase
from odoo.addons.sol_commerce.constants.models import MODEL_QUOTATION, MODEL_SALE_ORDER
from odoo.addons.sol_laboratory.constants.models import MODEL_IR_ACTIONS_ACT_WINDOW, MODEL_IR_UI_MENU, MODEL_PERSON
from odoo.addons.sol_laboratory.services.model_lookup import reference_as
from odoo.addons.sol_laboratory.tests.assertions import assert_instance


@tagged("post_install", "-at_install")
class TestSalesAnalysis(OrderCase):
    """The pipeline counts orders by stage, and the performance of each salesperson averages only the orders that
    reached each step."""

    def by_salesperson(self, user, action, orders):
        """The number of orders of each salesperson the user sees in the Pipeline or Performance analysis."""
        domain = literal_eval(
            assert_instance(
                reference_as(
                    self.env[MODEL_IR_ACTIONS_ACT_WINDOW], f"sol_commerce.action_medilab_sales_{action}"
                ).domain,
                str,
            )
        )
        groups = (
            self.env[MODEL_SALE_ORDER]
            .with_user(user)
            ._read_group(domain + [("id", "in", orders.ids)], ["user_id"], ["__count"])
        )
        return dict(groups)

    def test_each_order_is_counted_in_its_stage_and_finished_ones_leave_the_pipeline(self):
        unclaimed = self.make_order([(self.lead_product, 1)], status="submitted")
        draft = self.make_quotable_order()
        sent = self.sent_order()
        expired = self.sent_order()
        expired.payment_deadline = fields.Datetime.now() - timedelta(days=1)
        self.env[MODEL_QUOTATION]._flag_expired()
        declined = self.sent_order()
        declined._latest_quotation().action_decline("The price is above our budget.")
        accepted = self.sent_order()
        self.pay_advance(accepted)
        confirmed = self.make_confirmed_order()
        completed = self.make_confirmed_order()
        completed._set_status("completed")
        cart = self.make_order([(self.lead_product, 1)])
        cancelled = self.make_order([(self.lead_product, 1)], status="submitted")
        cancelled.action_customer_cancel()

        orders = (unclaimed, draft, sent, expired, declined, accepted, confirmed, completed, cart, cancelled)
        self.assertEqual(
            [order.pipeline_stage for order in orders],
            ["unclaimed", "draft", "sent", "sent", False, "accepted", "confirmed", False, False, False],
        )

    def test_revising_keeps_the_first_quotation_date(self):
        order = self.sent_order()
        first_sent_at = order.quoted_at
        order._latest_quotation().action_decline("Revise the quotation.")
        order.with_user(self.sales).action_revise_quotation()

        self.assertTrue(first_sent_at)
        self.assertEqual(order.quoted_at, first_sent_at)

    def test_durations_average_only_the_orders_that_reached_the_step(self):
        confirmed = self.make_confirmed_order()
        quoted = self.sent_order()
        confirmed.write(
            {
                "claimed_at": "2026-09-01 08:00:00",
                "accepted_at": "2026-09-04 08:00:00",
                "confirmed_at": "2026-09-05 08:00:00",
            }
        )
        confirmed.quotation_ids.write({"sent_at": "2026-09-02 08:00:00"})
        quoted.claimed_at = "2026-09-10 08:00:00"
        quoted.quotation_ids.write({"sent_at": "2026-09-14 08:00:00"})

        [figures] = self.env[MODEL_SALE_ORDER]._read_group(
            [("id", "in", (confirmed | quoted).ids)],
            [],
            ["days_to_quote:avg", "days_to_payment:avg", "days_to_confirmation:avg"],
        )
        self.assertEqual(figures, (2.5, 2.0, 1.0))
        self.assertEqual((confirmed.days_to_quote, quoted.days_to_payment), (1.0, 0.0))

    def test_quotations_sent_accepted_and_declined_and_the_revenue_of_confirmed_orders(self):
        confirmed = self.make_confirmed_order()
        declined = self.sent_order()
        declined._latest_quotation().action_decline("The price is above our budget.")
        declined.with_user(self.sales).action_revise_quotation()
        declined.with_user(self.sales).action_send_quotation()
        unpaid = self.sent_order()

        [figures] = self.env[MODEL_SALE_ORDER]._read_group(
            [("id", "in", (confirmed | declined | unpaid).ids)],
            [],
            ["quotation_sent_count:sum", "quotation_accepted_count:sum", "quotation_declined_count:sum", "revenue:sum"],
        )
        self.assertEqual(figures, (4, 1, 1, confirmed.amount_untaxed))
        self.assertTrue(confirmed.accepted_at and confirmed.confirmed_at)

    def test_a_salesperson_sees_their_own_figures_and_the_head_of_sales_everyones(self):
        mine = self.sent_order()
        theirs = self.sent_order()
        theirs.user_id = self.other_sales
        unclaimed = self.make_order([(self.lead_product, 1)], status="submitted")
        orders = mine | theirs | unclaimed
        nobody = self.env["res.users"]

        self.assertEqual(self.by_salesperson(self.sales, "pipeline", orders), {self.sales: 1, nobody: 1})
        self.assertEqual(self.by_salesperson(self.sales, "performance", orders), {self.sales: 1})
        self.assertEqual(
            self.by_salesperson(self.head, "pipeline", orders), {self.sales: 1, self.other_sales: 1, nobody: 1}
        )
        self.assertEqual(self.by_salesperson(self.head, "performance", orders), {self.sales: 1, self.other_sales: 1})

    def test_the_analyses_are_in_the_sales_app_for_those_who_read_orders_only(self):
        menus = self.env["ir.ui.menu"]
        sales_app = self.env.ref("sale.sale_menu_root")
        analyses = {
            reference_as(self.env[MODEL_IR_UI_MENU], f"sol_commerce.menu_sales_{name}").id
            for name in ("pipeline", "performance")
        }
        clerk = self.env[MODEL_PERSON].create({"name": "Hoang Van Duc", "login": "clerk.no.orders"}).user_id

        for user in (self.sales, self.head):
            self.assertLessEqual(analyses | {sales_app.id}, menus.with_user(user)._visible_menu_ids())
        self.assertFalse(analyses & menus.with_user(clerk)._visible_menu_ids())
